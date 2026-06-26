"""
extractor.py — Extrae datos de facturas electrónicas DIAN (XML UBL, PDF, ZIP).
Importado por gmail_facturas.py y server.py.
"""

import os, re, zipfile, tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

try:
    import fitz
    _FITZ = True
except ImportError:
    _FITZ = False

# ── Namespaces UBL DIAN ───────────────────────────────────────────────────────

UBL_NS = "urn:oasis:names:specification:ubl:schema:xsd"

NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}

PATRON_CUFE        = re.compile(r"\b([a-f0-9]{96})\b", re.IGNORECASE)
PATRON_NUM_FACTURA = re.compile(r"^[A-Za-z]{1,4}[-]?\d{3,}$")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _xt(root, xpath):
    el = root.find(xpath, NS)
    return el.text.strip() if el is not None and el.text else None


# ── Descomprimir ZIP ──────────────────────────────────────────────────────────

def descomprimir_zip(data: bytes, destino: Path) -> list:
    """Descomprime ZIP en memoria, guarda PDF/XML en destino. Retorna lista de Paths."""
    archivos = []
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        with zipfile.ZipFile(tmp_path, "r") as z:
            for nombre in z.namelist():
                if nombre.lower().endswith((".pdf", ".xml")):
                    z.extract(nombre, destino)
                    archivos.append(destino / nombre)
        os.unlink(tmp_path)
    except Exception as e:
        print(f"Error descomprimiendo ZIP: {e}")
    archivos.sort(key=lambda p: 0 if p.suffix.lower() == ".xml" else 1)
    return archivos


# ── Extracción XML (UBL DIAN) ─────────────────────────────────────────────────

def _strip_ns(root):
    """Elimina namespace URIs de todos los tags para búsqueda universal."""
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}")[1]
    return root


def _find_text(root, *tags):
    """Busca el primer elemento que coincida con cualquiera de los tags locales."""
    for tag in tags:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            return el.text.strip()
    return None


def _find_under(root, parent_tag, *child_tags):
    """Busca child_tag dentro del primer parent_tag encontrado."""
    parent = root.find(f".//{parent_tag}")
    if parent is None:
        return None
    for tag in child_tags:
        el = parent.find(f".//{tag}")
        if el is not None and el.text:
            return el.text.strip()
    return None


def _find_max(root, tag):
    """Retorna el valor máximo de todos los elementos con ese tag (evita tomar línea de detalle)."""
    vals = [float(el.text) for el in root.findall(f".//{tag}") if el.text]
    return max(vals, default=0)


def extraer_xml(path: str) -> dict | None:
    try:
        root = _strip_ns(ET.parse(path).getroot())
    except Exception as e:
        print(f"Error XML: {e}")
        return None

    # Verificar que sea un documento DIAN (tiene UUID = CUFE)
    cufe_el = root.find(".//UUID")
    if cufe_el is None:
        return None

    def to_float(v):
        try: return float(v) if v else 0
        except: return 0

    # Número de factura
    numero_factura = None
    for el in root.findall(".//ID"):
        val = (el.text or "").strip()
        if val and PATRON_NUM_FACTURA.match(val):
            numero_factura = val
            break

    # Proveedor (emisor)
    prov_nit    = _find_under(root, "AccountingSupplierParty", "CompanyID", "ID")
    prov_nombre = _find_under(root, "AccountingSupplierParty", "RegistrationName", "Name")
    prov_ciudad = _find_under(root, "AccountingSupplierParty", "CityName")

    # Receptor (cliente) — empresa (CompanyID) o persona natural (ID con CC)
    rec_nit    = _find_under(root, "AccountingCustomerParty", "CompanyID", "ID")
    rec_nombre = _find_under(root, "AccountingCustomerParty", "RegistrationName", "Name")
    if not rec_nombre:
        first = _find_under(root, "AccountingCustomerParty", "FirstName")
        last  = _find_under(root, "AccountingCustomerParty", "FamilyName") or \
                _find_under(root, "AccountingCustomerParty", "LastName")
        rec_nombre = " ".join(filter(None, [first, last])) or None

    # Montos — máximo de cada campo (el total del documento > líneas de detalle)
    subtotal = _find_max(root, "LineExtensionAmount")
    total    = _find_max(root, "PayableAmount")
    # IVA: buscar en TaxTotal primero
    iva_el = root.find(".//TaxTotal//TaxAmount")
    iva = to_float(iva_el.text if iva_el is not None else None)

    datos = {
        "cufe":              cufe_el.text.strip(),
        "numero":            numero_factura,
        "fecha":             _find_text(root, "IssueDate"),
        "proveedor_nit":     prov_nit,
        "proveedor_nombre":  prov_nombre,
        "proveedor_ciudad":  prov_ciudad,
        "receptor_nit":      rec_nit,
        "receptor_nombre":   rec_nombre,
        "subtotal":          subtotal,
        "iva":               iva,
        "total_factura":     total,
    }
    datos["valor_neto"] = total
    return datos if datos.get("numero") else None


# ── Extracción PDF ────────────────────────────────────────────────────────────

def extraer_pdf(path: str) -> dict | None:
    if not _FITZ:
        print("PyMuPDF no disponible: pip install pymupdf")
        return None
    try:
        text = "\n".join(p.get_text() for p in fitz.open(path))
    except Exception as e:
        print(f"Error PDF: {e}")
        return None

    def parse_monto(s):
        try:
            s = s.strip()
            # Eliminar parte decimal (,XX o .XX al final) antes de limpiar separadores
            s = re.sub(r'[.,]\d{1,2}$', '', s)
            return int(s.replace(".", "").replace(",", ""))
        except: return 0

    datos = {}

    m = PATRON_CUFE.search(text)
    if m:
        datos["cufe"] = m.group(1)

    m = re.search(r"(?:Factura(?:\s+electr[oó]nica)?|N[oº°]\.?)[:\s#]*([A-Z]{2,4}[-\s]?\d{4,})", text, re.IGNORECASE)
    if m:
        datos["numero"] = m.group(1).strip()

    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if not m:
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
        if m:
            datos["fecha"] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    else:
        datos["fecha"] = m.group(1)

    # Todos los NITs del documento (primero = proveedor, segundo = receptor si existe)
    nit_matches = re.findall(r"NIT[:\s]*([\d\.]{6,}(?:\-\d)?)", text, re.IGNORECASE)
    if nit_matches:
        datos["proveedor_nit"] = nit_matches[0]
        if len(nit_matches) > 1:
            datos["receptor_nit"] = nit_matches[1]

    # CC del receptor (persona natural) — buscar después del primer NIT
    if not datos.get("receptor_nit"):
        proveedor_pos = text.upper().find("NIT")
        buscar_desde  = proveedor_pos + 10 if proveedor_pos >= 0 else 0
        m_cc = re.search(r"\bC\.?C\.?\b[:\s]*([\d\.]{6,12})", text[buscar_desde:], re.IGNORECASE)
        if m_cc:
            datos["receptor_nit"] = m_cc.group(1)

    # Nombre del receptor — buscar "Señores:", "Cliente:", no encabezados de tabla
    m_nom = re.search(r"(?:Se[ñn]ore?s|Cliente)[:\s]+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\s]{4,60})(?:\n|$)", text, re.IGNORECASE)
    if m_nom:
        datos["receptor_nombre"] = m_nom.group(1).strip()

    # Total: acepta "TOTAL A PAGAR", "TOTAL A PAGAR CLIENTE", "TOTAL OPERACIÓN", "TOTAL FACTURA"
    m = re.search(r"TOTAL\s+(?:A\s+PAGAR(?:\s+\w+)?|FACTURA|OPERACI[OÓ]N\s+COP)[^\d\n]*([\d\.,]{4,})", text, re.IGNORECASE)
    if m:
        datos["total_factura"] = parse_monto(m.group(1))
        datos["valor_neto"]    = datos["total_factura"]

    m = re.search(r"(?:Subtotal|Base\s+gravable)[:\s\$]*([\d\.,]{4,})", text, re.IGNORECASE)
    if m:
        datos["subtotal"] = parse_monto(m.group(1))

    # IVA: buscar valor monetario (mínimo 4 dígitos), no el porcentaje (2 dígitos)
    m = re.search(r"IVA\s*(?:\d{1,2}[.,]\d{2}\s*%[^\d]*)?([\d\.,]{4,})", text, re.IGNORECASE)
    if m:
        datos["iva"] = parse_monto(m.group(1))

    return datos if datos.get("numero") or datos.get("cufe") else None


# ── Detectar o crear empresa por NIT receptor ─────────────────────────────────

COLORES = ["#6366f1","#10b981","#f59e0b","#ef4444","#3b82f6","#8b5cf6","#ec4899","#14b8a6"]
ICONOS  = ["🏢","🏭","🛒","🏗️","💊","🚛","🍽️","📦","⚙️","🏬"]

def detectar_empresa(receptor_nit: str, sb) -> dict | None:
    """Busca en Supabase la empresa cuyo NIT coincide con el receptor."""
    if not receptor_nit:
        return None
    nit_limpio = re.sub(r"[^\d]", "", receptor_nit)
    empresas = sb.table("empresas_clientes").select("id,nit,razon_social").execute().data
    for e in empresas:
        if re.sub(r"[^\d]", "", e.get("nit", "")) == nit_limpio:
            return e
    return None

def detectar_o_crear_empresa(datos: dict, sb) -> dict | None:
    """
    Busca la empresa por NIT receptor. Si no existe retorna None
    (el llamador debe avisar por Telegram para que Eduardo la agregue manualmente).
    """
    receptor_nit = datos.get("receptor_nit", "")
    if not receptor_nit:
        return None
    return detectar_empresa(receptor_nit, sb)


def guardar_empresa_pendiente(datos: dict, fuente: str, sb) -> str | None:
    """
    Guarda los datos de una factura con empresa desconocida en empresas_pendientes.
    Retorna el UUID de la fila creada, o None si falla.
    """
    try:
        import json as _json
        # Serializar datos (los valores float pueden causar problemas)
        factura_json = {k: (float(v) if isinstance(v, (int, float)) else v)
                        for k, v in (datos or {}).items()}
        res = sb.table("empresas_pendientes").insert({
            "nit":          datos.get("receptor_nit", ""),
            "razon_social": datos.get("receptor_nombre", ""),
            "ciudad":       datos.get("receptor_ciudad", ""),
            "factura_data": factura_json,
            "fuente":       fuente,
        }).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        print(f"Error guardando empresa pendiente: {e}")
        return None
