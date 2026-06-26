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

def extraer_xml(path: str) -> dict | None:
    try:
        root = ET.parse(path).getroot()
    except Exception as e:
        print(f"Error XML: {e}")
        return None

    if UBL_NS not in root.tag and UBL_NS not in str(root.attrib):
        return None

    def to_float(v):
        try: return float(v) if v else 0
        except: return 0

    numero_factura = None
    for el in root.iter("{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID"):
        val = (el.text or "").strip()
        if val and PATRON_NUM_FACTURA.match(val):
            numero_factura = val
            break

    datos = {
        "cufe":              _xt(root, ".//cbc:UUID"),
        "numero":            numero_factura,
        "fecha":             _xt(root, ".//cbc:IssueDate"),
        "proveedor_nit":     _xt(root, ".//cac:AccountingSupplierParty//cbc:CompanyID"),
        "proveedor_nombre":  _xt(root, ".//cac:AccountingSupplierParty//cbc:RegistrationName"),
        "proveedor_ciudad":  _xt(root, ".//cac:AccountingSupplierParty//cbc:CityName"),
        "receptor_nit":      _xt(root, ".//cac:AccountingCustomerParty//cbc:CompanyID"),
        "receptor_nombre":   _xt(root, ".//cac:AccountingCustomerParty//cbc:RegistrationName"),
        "subtotal":          to_float(_xt(root, ".//cbc:LineExtensionAmount")),
        "iva":               to_float(_xt(root, ".//cbc:TaxAmount")),
        "total_factura":     to_float(_xt(root, ".//cbc:PayableAmount")),
    }
    datos["valor_neto"] = datos["total_factura"]
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
        try: return int(s.replace(".", "").replace(",", "").strip())
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

    m = re.search(r"NIT[:\s]*([\d\.]{6,}(?:\-\d)?)", text, re.IGNORECASE)
    if m:
        datos["proveedor_nit"] = m.group(1)

    m = re.search(r"(?:TOTAL\s+(?:A\s+PAGAR|FACTURA)|Valor\s+total)[:\s\$]*([\d\.,]+)", text, re.IGNORECASE)
    if m:
        datos["total_factura"] = parse_monto(m.group(1))
        datos["valor_neto"]    = datos["total_factura"]

    m = re.search(r"(?:Subtotal|Base\s+gravable)[:\s\$]*([\d\.,]+)", text, re.IGNORECASE)
    if m:
        datos["subtotal"] = parse_monto(m.group(1))

    m = re.search(r"IVA[:\s\$]*([\d\.,]+)", text, re.IGNORECASE)
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
