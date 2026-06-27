"""
extractor.py — Extrae datos de facturas electrónicas DIAN (XML UBL, PDF, ZIP).
Importado por gmail_facturas.py y server.py.
"""

import os, re, zipfile, tempfile, logging
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
            destino_abs = Path(destino).resolve()
            for nombre in z.namelist():
                if not nombre.lower().endswith((".pdf", ".xml")):
                    continue
                target = (destino_abs / nombre).resolve()
                if not str(target).startswith(str(destino_abs)):
                    continue  # Zip Slip bloqueado
                if z.getinfo(nombre).file_size > 50 * 1024 * 1024:
                    continue  # Zip Bomb bloqueado
                z.extract(nombre, destino)
                archivos.append(destino / nombre)
        os.unlink(tmp_path)
    except Exception as e:
        logging.exception("Error descomprimiendo ZIP")
    archivos.sort(key=lambda p: 0 if p.suffix.lower() == ".xml" else 1)
    return archivos


# ── Extracción XML (UBL DIAN) ─────────────────────────────────────────────────

def _strip_ns(root):
    """Elimina namespace URIs de todos los tags para búsqueda universal."""
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}")[1]
    return root


def _limpiar_nombre(nombre: str) -> str | None:
    """Elimina palabras de label/encabezado que no deben estar en un nombre de empresa."""
    if not nombre:
        return None
    # Quitar sufijos que no son parte del nombre (NIT, CC, Dirección, etc.)
    nombre = re.sub(r'\s+(NIT|C\.?C\.?|RUT|Direcci[oó]n|Calle|Carrera|Cr\.?|Cl\.?|Av\.?|Tel[eé]fono|Tel\.?)\b.*',
                    '', nombre, flags=re.IGNORECASE).strip()
    # Quitar prefijos de label
    nombre = re.sub(r'^(Nombre|Cliente|Se[ñn]ores?)[:\s]+', '', nombre, flags=re.IGNORECASE).strip()
    return nombre if len(nombre) > 2 else None


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


def _extraer_documento_embebido(outer_root) -> "tuple[ET.Element, str] | tuple[None, str]":
    """
    Extrae el documento UBL embebido en <Description> de un AttachedDocument DIAN.
    Soporta Invoice (facturas), CreditNote (NC tipo 91) y DebitNote (ND tipo 92).
    Retorna (elemento, tipo_documento).
    """
    TIPOS = [
        ("<Invoice",    "factura"),
        ("<CreditNote", "nota_credito"),
        ("<DebitNote",  "nota_debito"),
    ]
    for el in outer_root.iter():
        tag = el.tag.split("}")[1] if "}" in el.tag else el.tag
        if tag == "Description" and el.text:
            texto = el.text.strip()
            for marca, tipo_doc in TIPOS:
                if marca in texto:
                    try:
                        inner = ET.fromstring(texto)
                        return _strip_ns(inner), tipo_doc
                    except Exception as e:
                        logging.warning("Error parseando %s embebido: %s", tipo_doc, e)
    return None, "factura"


def extraer_xml(path: str) -> dict | None:
    try:
        raw_root = ET.parse(path).getroot()
    except Exception as e:
        logging.exception("Error XML")
        return None

    # Detectar AttachedDocument DIAN y extraer documento interno (Invoice/CreditNote/DebitNote)
    outer_tag = raw_root.tag.split("}")[1] if "}" in raw_root.tag else raw_root.tag
    tipo_documento = "factura"
    if outer_tag == "AttachedDocument":
        invoice_root, tipo_documento = _extraer_documento_embebido(raw_root)
        outer_root = _strip_ns(raw_root)
    else:
        invoice_root = None
        outer_root   = None
        # Detectar tipo por tag raíz directo
        if "CreditNote" in outer_tag:
            tipo_documento = "nota_credito"
        elif "DebitNote" in outer_tag:
            tipo_documento = "nota_debito"

    root = invoice_root if invoice_root is not None else _strip_ns(raw_root)

    # Verificar que sea un documento DIAN (tiene UUID = CUFE)
    cufe_el = root.find(".//UUID")
    if cufe_el is None and outer_root is not None:
        cufe_el = outer_root.find(".//UUID")
    if cufe_el is None:
        return None

    def to_float(v):
        try: return float(v) if v else 0
        except: return 0

    # ── Número de factura ───────────────────────────────────────────────────────
    # En AttachedDocument el número real está en ParentDocumentID del sobre
    numero_factura = None
    if outer_root is not None:
        pid = outer_root.find(".//ParentDocumentID")
        if pid is not None and pid.text:
            numero_factura = pid.text.strip()
    if not numero_factura:
        for el in root.findall(".//ID"):
            val = (el.text or "").strip()
            if val and PATRON_NUM_FACTURA.match(val):
                numero_factura = val
                break

    # ── Proveedor (emisor) ──────────────────────────────────────────────────────
    prov_nit    = _find_under(root, "AccountingSupplierParty", "CompanyID", "ID")
    prov_nombre = _limpiar_nombre(_find_under(root, "AccountingSupplierParty", "RegistrationName", "Name"))
    prov_ciudad = _find_under(root, "AccountingSupplierParty", "CityName")

    # Fallback: NITs del sobre AttachedDocument (primer CompanyID = proveedor)
    if not prov_nit and outer_root is not None:
        all_company_ids = [e.text.strip() for e in outer_root.findall(".//CompanyID") if e.text]
        if all_company_ids:
            prov_nit = all_company_ids[0]

    # ── Receptor (cliente) ──────────────────────────────────────────────────────
    rec_nit    = _find_under(root, "AccountingCustomerParty", "CompanyID", "ID")
    rec_nombre = _find_under(root, "AccountingCustomerParty", "RegistrationName", "Name")
    if not rec_nombre:
        first = _find_under(root, "AccountingCustomerParty", "FirstName")
        last  = _find_under(root, "AccountingCustomerParty", "FamilyName") or \
                _find_under(root, "AccountingCustomerParty", "LastName")
        rec_nombre = " ".join(filter(None, [first, last])) or None
    rec_nombre = _limpiar_nombre(rec_nombre)

    # Fallback: segundo CompanyID del sobre AttachedDocument = receptor
    if not rec_nit and outer_root is not None:
        all_company_ids = [e.text.strip() for e in outer_root.findall(".//CompanyID") if e.text]
        if len(all_company_ids) >= 2:
            rec_nit = all_company_ids[1]

    # ── Montos desde LegalMonetaryTotal (totales del documento, no líneas) ──────
    lmt = root.find(".//LegalMonetaryTotal")
    if lmt is not None:
        def lmt_val(tag):
            el = lmt.find(f".//{tag}")
            return to_float(el.text if el is not None else None)
        subtotal = lmt_val("LineExtensionAmount")
        total    = lmt_val("PayableAmount") or lmt_val("TaxInclusiveAmount")
    else:
        subtotal = _find_max(root, "LineExtensionAmount")
        total    = _find_max(root, "PayableAmount")

    # IVA: máximo TaxAmount (el valor total del impuesto, más alto que subtotales por línea)
    iva = _find_max(root, "TaxAmount")

    # Código DIAN del tipo de documento (01 factura, 03 doc equivalente, 91 NC, 92 ND, etc.)
    tipo_dian = (
        _find_text(root, "InvoiceTypeCode") or
        _find_text(root, "CreditNoteTypeCode") or
        _find_text(root, "DebitNoteTypeCode") or
        ("91" if tipo_documento == "nota_credito" else
         "92" if tipo_documento == "nota_debito" else "01")
    )

    # Referencia a factura original (solo en Notas de Crédito/Débito)
    referencia_nc = None
    if tipo_documento in ("nota_credito", "nota_debito"):
        referencia_nc = _find_under(root, "BillingReference", "ID") or \
                        _find_under(root, "InvoiceDocumentReference", "ID")

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
        "tipo_documento":    tipo_documento,
        "tipo_dian":         tipo_dian,
        "referencia_nc":     referencia_nc,
    }
    datos["valor_neto"] = total
    return datos if datos.get("numero") else None


# ── Lógica de flujo venta/gasto ───────────────────────────────────────────────

# Tipos DIAN que SIEMPRE son gastos (empresa siempre es el receptor)
_TIPOS_SIEMPRE_GASTO = {"03", "05", "06"}

def determinar_flujo(datos: dict, empresa_nit: str) -> str:
    """
    Determina si el documento es VENTA o GASTO para la empresa.

    Tipos DIAN:
      01 Factura venta | 02 Exportación | 04 Contingencia
      91 NC            | 92 ND
      03 Doc equivalente (tiquetes) → siempre GASTO
      05 Doc soporte (no obligados) → siempre GASTO
      06 Nota ajuste DS             → siempre GASTO

    Regla: si la empresa es el PROVEEDOR/EMISOR → VENTA
           si la empresa es el RECEPTOR          → GASTO
    """
    if datos.get("tipo_dian") in _TIPOS_SIEMPRE_GASTO:
        return "gasto"
    empresa_base = _nit_base(empresa_nit)
    prov_base    = _nit_base(datos.get("proveedor_nit", ""))
    if empresa_base and prov_base and empresa_base == prov_base:
        return "venta"
    return "gasto"


def guardar_factura(datos: dict, empresa_id: int, empresa_nit: str,
                    archivo: str, fuente: str, sb) -> tuple:
    """
    Guarda en facturas_venta o facturas_gastos según el rol de la empresa.
    Retorna (flujo: 'venta'|'gasto', resultado: 'nueva'|'duplicada').
    """
    from datetime import date as _date
    flujo  = determinar_flujo(datos, empresa_nit)
    tabla  = "facturas_venta" if flujo == "venta" else "facturas_gastos"
    numero = datos.get("numero", "")

    ya = sb.table(tabla).select("id").eq("empresa_id", empresa_id).eq("numero", numero).execute()
    if ya.data:
        return flujo, "duplicada"

    tipo_doc = datos.get("tipo_documento", "factura")
    if tipo_doc == "nota_credito":
        estado = "POR_DEVOLVER" if flujo == "venta" else "POR_RECIBIR"
    else:
        estado = "PENDIENTE"

    row = {
        "empresa_id":     empresa_id,
        "numero":         numero,
        "cufe":           datos.get("cufe", ""),
        "fecha":          datos.get("fecha") or str(_date.today()),
        "subtotal":       float(datos.get("subtotal") or 0),
        "iva":            float(datos.get("iva") or 0),
        "total_factura":  float(datos.get("total_factura") or 0),
        "valor_neto":     float(datos.get("valor_neto") or datos.get("total_factura") or 0),
        "estado":         estado,
        "archivo_pdf":    archivo,
        "fuente":         fuente,
        "tipo_documento": tipo_doc,
        "tipo_dian":      datos.get("tipo_dian", "01"),
        "referencia_nc":  datos.get("referencia_nc"),
    }

    if flujo == "venta":
        row.update({
            "cliente_nit":    datos.get("receptor_nit", ""),
            "cliente_nombre": datos.get("receptor_nombre", ""),
            "cliente_ciudad": datos.get("proveedor_ciudad", ""),
        })
    else:
        row.update({
            "proveedor_nit":    datos.get("proveedor_nit", ""),
            "proveedor_nombre": datos.get("proveedor_nombre", ""),
            "proveedor_ciudad": datos.get("proveedor_ciudad", ""),
        })

    sb.table(tabla).insert(row).execute()
    return flujo, "nueva"


# ── Extracción PDF ────────────────────────────────────────────────────────────

def extraer_pdf(path: str) -> dict | None:
    if not _FITZ:
        logging.warning("PyMuPDF no disponible: pip install pymupdf")
        return None
    try:
        with fitz.open(path) as doc:
            text = "\n".join(p.get_text() for p in doc)
    except Exception as e:
        logging.exception("Error PDF")
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
        datos["receptor_nombre"] = _limpiar_nombre(m_nom.group(1).strip())

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

def _nit_base(nit: str) -> str:
    """Extrae dígitos del NIT ignorando el dígito verificador (parte después del guion)."""
    if not nit:
        return ""
    # Si tiene guion, descartar lo que va después del último guion (dígito verificador)
    if "-" in nit:
        nit = nit.rsplit("-", 1)[0]
    return re.sub(r"[^\d]", "", nit)


def detectar_empresa(receptor_nit: str, sb, contador_id=None) -> dict | None:
    """Busca en Supabase la empresa cuyo NIT coincide con el receptor."""
    if not receptor_nit:
        return None
    nit_factura = _nit_base(receptor_nit)
    if not nit_factura:
        return None
    q = sb.table("empresas_clientes").select("id,nit,razon_social,contador_id")
    if contador_id:
        q = q.eq("contador_id", contador_id)
    empresas = q.execute().data
    for e in empresas:
        nit_empresa = _nit_base(e.get("nit", ""))
        # Coincide si son iguales o uno empieza con el otro (variantes con/sin verificador)
        if nit_factura == nit_empresa or nit_factura.startswith(nit_empresa) or nit_empresa.startswith(nit_factura):
            return e
    return None

def detectar_o_crear_empresa(datos: dict, sb, contador_id=None) -> dict | None:
    """
    Busca la empresa por NIT receptor (gasto) o proveedor (venta).
    Primero intenta receptor (caso más común). Si no, intenta proveedor
    para cuando la empresa es quien emite la factura (ventas).
    """
    empresa = detectar_empresa(datos.get("receptor_nit", ""), sb, contador_id)
    if empresa:
        return empresa
    return detectar_empresa(datos.get("proveedor_nit", ""), sb, contador_id)


def subir_a_storage(ruta_local: str, empresa_id: int, numero: str, fecha: str, sb) -> str | None:
    """
    Sube el archivo a Supabase Storage en facturas/{empresa_id}/{YYYY-MM}/{numero}.ext
    Retorna la URL pública, o None si falla.
    """
    try:
        import mimetypes
        ruta = Path(ruta_local)
        if not ruta.exists():
            return None
        ext = ruta.suffix.lower()
        # Determinar mes del folder
        mes_folder = fecha[:7] if fecha and len(fecha) >= 7 else "sin-fecha"
        storage_path = f"{empresa_id}/{mes_folder}/{numero}{ext}"
        mime_type = mimetypes.guess_type(str(ruta))[0] or "application/octet-stream"
        with open(ruta, "rb") as f:
            sb.storage.from_("facturas").upload(
                path=storage_path,
                file=f.read(),
                file_options={"content-type": mime_type, "upsert": "true"},
            )
        # Obtener URL pública
        url = sb.storage.from_("facturas").get_public_url(storage_path)
        return url
    except Exception as e:
        logging.exception("Error subiendo a Storage")
        return None


def guardar_empresa_pendiente(datos: dict, fuente: str, sb, contador_id=None) -> str | None:
    """
    Guarda los datos de una factura con empresa desconocida en empresas_pendientes.
    Retorna el UUID de la fila creada, o None si falla.
    """
    try:
        import json as _json
        factura_json = {k: (float(v) if isinstance(v, (int, float)) else v)
                        for k, v in (datos or {}).items()}
        row = {
            "nit":          datos.get("receptor_nit", ""),
            "razon_social": datos.get("receptor_nombre", ""),
            "ciudad":       datos.get("receptor_ciudad", ""),
            "factura_data": factura_json,
            "fuente":       fuente,
        }
        if contador_id:
            row["contador_id"] = contador_id
        res = sb.table("empresas_pendientes").insert(row).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        logging.exception("Error guardando empresa pendiente")
        return None
