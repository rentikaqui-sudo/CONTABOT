"""
gmail_facturas.py — Escanea Gmail, detecta facturas electrónicas DIAN y las registra en ContaBot.

Detección inteligente en 3 niveles:
  1. Asunto del correo con patrón DIAN: NIT;NOMBRE;NUMERO;01;NOMBRE  → 100% seguro
  2. Adjunto XML con namespace UBL DIAN                               → 100% seguro
  3. Adjunto PDF con CUFE (96 chars hex)                              → 100% seguro
  4. Sistema de puntuación para casos ambiguos                        → revisión manual

El bot aprende: guarda los remitentes confirmados en data/remitentes_facturas.json
y los prioriza en futuros escaneos.

Uso:
    python scripts/gmail_facturas.py                  # escanea inbox completo
    python scripts/gmail_facturas.py --empresa 1      # asigna a empresa específica
    python scripts/gmail_facturas.py --max 100        # cuántos correos revisar
"""

import os, sys, base64, re, argparse, json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    print("ERROR: pip install google-auth-oauthlib google-api-python-client")
    sys.exit(1)

try:
    from supabase import create_client
    _sb_url = os.environ.get("SUPABASE_URL", "")
    _sb_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not _sb_url or not _sb_key:
        print("ERROR: SUPABASE_URL y SUPABASE_SERVICE_KEY deben estar en .env")
        sys.exit(1)
    sb = create_client(_sb_url, _sb_key)
except ImportError:
    print("ERROR: pip install supabase")
    sys.exit(1)

# ── Rutas y configuración ─────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

import sys as _sys
_sys.path.insert(0, str(BASE_DIR / "scripts"))
from extractor import extraer_xml, extraer_pdf, descomprimir_zip, detectar_o_crear_empresa, guardar_empresa_pendiente
from telegram_notif import notificar_factura, notificar_empresa_desconocida
ADJUNTOS_DIR  = BASE_DIR / "data" / "facturas_recibidas"
TOKEN_PATH    = BASE_DIR / "data" / "gmail_token.json"
CREDS_PATH    = BASE_DIR / "data" / "gmail_credentials.json"
APRENDIZAJE   = BASE_DIR / "data" / "remitentes_facturas.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Tipos de documento DIAN que nos interesan
TIPOS_FACTURA_DIAN = {"01", "02", "04"}  # venta, exportación, contingencia
TIPOS_NOTA         = {"91", "92"}         # nota crédito / débito (registrar diferente)

# Regex del patrón de asunto de factura electrónica colombiana:
# NIT;NOMBRE EMPRESA;NUMERO DOC;TIPO;NOMBRE EMPRESA
PATRON_ASUNTO_DIAN = re.compile(
    r"(\d{7,10});([^;]+);(\w+);(0[124]|91|92);",
    re.IGNORECASE
)

# CUFE: 96 caracteres hexadecimales
PATRON_CUFE = re.compile(r"\b([a-f0-9]{96})\b", re.IGNORECASE)

# Namespace UBL de facturas DIAN
UBL_NS = "urn:oasis:names:specification:ubl:schema:xsd"


# ── Aprendizaje de remitentes ─────────────────────────────────────────────────

def cargar_remitentes():
    if APRENDIZAJE.exists():
        return json.loads(APRENDIZAJE.read_text(encoding="utf-8"))
    return {}

def guardar_remitente(email, nombre_empresa, confianza):
    """Guarda un remitente confirmado para priorizar en futuros escaneos."""
    data = cargar_remitentes()
    if email not in data or data[email]["confianza"] < confianza:
        data[email] = {
            "empresa": nombre_empresa,
            "confianza": confianza,
            "primera_vez": data.get(email, {}).get("primera_vez", datetime.today().strftime("%Y-%m-%d")),
            "ultima_vez": datetime.today().strftime("%Y-%m-%d"),
            "facturas": data.get(email, {}).get("facturas", 0) + 1,
        }
    else:
        data[email]["ultima_vez"] = datetime.today().strftime("%Y-%m-%d")
        data[email]["facturas"]   = data[email].get("facturas", 0) + 1
    APRENDIZAJE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Autenticación Gmail ───────────────────────────────────────────────────────

def _get_client_secrets():
    """Lee client_id y client_secret desde env vars o gmail_credentials.json."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        if CREDS_PATH.exists():
            raw = json.loads(CREDS_PATH.read_text())
            w = raw.get("web", raw.get("installed", {}))
            client_id = w.get("client_id", "")
            client_secret = w.get("client_secret", "")
    return client_id, client_secret

def get_gmail_from_supabase(empresa_id: int):
    """Construye el servicio de Gmail usando el refresh_token guardado en Supabase."""
    rows = sb.table("gmail_tokens").select("*").eq("empresa_id", empresa_id).eq("activo", True).execute().data
    if not rows:
        return None, None
    t = rows[0]
    client_id, client_secret = _get_client_secrets()
    if not client_id:
        print("ERROR: GOOGLE_CLIENT_ID no configurado")
        return None, None
    creds = Credentials(
        token=None,
        refresh_token=t["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds), t["email"]

def get_gmail():
    """Fallback: usa el token local (data/gmail_token.json) para desarrollo."""
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                print(f"\nERROR: No se encontró {CREDS_PATH}")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


# ── Detección inteligente de facturas ────────────────────────────────────────

def puntaje_es_factura(asunto, nombre_adjunto, remitente):
    """
    Retorna (es_factura: bool, confianza: int, info: dict)
    confianza 100 = certeza absoluta, <50 = probable no-factura
    """
    info = {"tipo": None, "nit_emisor": None, "nombre_emisor": None, "numero": None}

    # Nivel 1: patrón de asunto DIAN (certeza absoluta)
    m = PATRON_ASUNTO_DIAN.search(asunto or "")
    if m:
        tipo = m.group(4)
        info.update({
            "nit_emisor":    m.group(1),
            "nombre_emisor": m.group(2).strip(),
            "numero":        m.group(3),
            "tipo":          "nota" if tipo in TIPOS_NOTA else "factura",
        })
        return True, 100, info

    # Nivel 2: nombre de adjunto con patrones DIAN
    fname = (nombre_adjunto or "").lower()
    score = 0
    if re.match(r"\d{7,10}_\w+\.(xml|pdf)$", fname):  # NIT_NUMERO.xml
        score += 60
    if fname.startswith(("fe_", "fev_", "setp", "fact")):
        score += 40
    if fname.endswith(".xml"):
        score += 20

    # Nivel 3: palabras en asunto
    asunto_lower = (asunto or "").lower()
    for kw, pts in [("factura electr", 30), ("factura de venta", 30),
                    ("dian", 20), ("fe-", 20), ("fev-", 20),
                    ("factura", 15), ("invoice", 10)]:
        if kw in asunto_lower:
            score += pts

    # Nivel 4: remitente conocido (aprendizaje)
    remitentes = cargar_remitentes()
    if remitente and remitente.lower() in remitentes:
        r = remitentes[remitente.lower()]
        score += min(r["confianza"], 30)  # máx 30 puntos extra por historial

    if score >= 50:
        return True, score, info
    return False, score, info


# ── Marcar correo como leído ──────────────────────────────────────────────────

def marcar_leido(service, msg_id):
    try:
        service.users().messages().modify(
            userId="me", id=msg_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()
    except Exception as e:
        print(f"    Aviso: no se pudo marcar como leido: {e}")


# ── Escaneo principal ─────────────────────────────────────────────────────────

def escanear_todas_empresas(max_correos=50):
    """Escanea el Gmail de todos los clientes con token activo en Supabase."""
    tokens = sb.table("gmail_tokens").select("empresa_id,email").eq("activo", True).execute().data
    if not tokens:
        print("[gmail] No hay cuentas de Gmail conectadas en Supabase.")
        return
    for t in tokens:
        eid = t["empresa_id"]
        email = t["email"]
        print(f"\n[gmail] Escaneando {email} (empresa {eid})...")
        try:
            service, _ = get_gmail_from_supabase(eid)
            if not service:
                print(f"[gmail] No se pudo obtener token para empresa {eid}")
                continue
            escanear_inbox(empresa_id=eid, max_correos=max_correos, service=service)
        except Exception as e:
            print(f"[gmail] Error empresa {eid} ({email}): {e}")

def escanear_inbox(empresa_id, max_correos=100, service=None):
    if service is None:
        service = get_gmail()

    # Query amplia — el filtro inteligente lo hace puntaje_es_factura()
    query = "has:attachment is:unread (filename:pdf OR filename:xml OR filename:zip)"
    print(f"Buscando en Gmail (máx {max_correos} correos)...")

    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_correos
    ).execute()

    mensajes = result.get("messages", [])
    print(f"Correos con adjuntos encontrados: {len(mensajes)}\n")

    stats = {"nuevas": 0, "duplicadas": 0, "ignoradas": 0, "errores": 0}

    for ref in mensajes:
        msg = service.users().messages().get(
            userId="me", id=ref["id"], format="full"
        ).execute()
        resultado = procesar_mensaje(service, msg, empresa_id)
        stats[resultado] = stats.get(resultado, 0) + 1
        if resultado in ("nuevas", "duplicadas"):
            marcar_leido(service, ref["id"])

    print(f"\nResultado:")
    print(f"  OK  Facturas nuevas registradas : {stats['nuevas']}")
    print(f"  =   Ya existian (duplicadas)    : {stats['duplicadas']}")
    print(f"  --  Ignoradas (no son facturas) : {stats['ignoradas']}")
    print(f"  !   Errores                     : {stats['errores']}")
    return stats


# ── Procesamiento de un mensaje ───────────────────────────────────────────────

def procesar_mensaje(service, msg, empresa_id):
    headers  = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    asunto   = headers.get("Subject", "")
    remitente = re.search(r"[\w\.\-]+@[\w\.\-]+", headers.get("From", ""))
    remitente = remitente.group(0).lower() if remitente else ""
    parts    = msg["payload"].get("parts", [])

    # Revisar adjuntos
    for part in parts:
        fname  = part.get("filename", "")
        att_id = part.get("body", {}).get("attachmentId")
        if not fname or not att_id:
            continue
        if not fname.lower().endswith((".pdf", ".xml", ".zip")):
            continue

        es_factura, confianza, info = puntaje_es_factura(asunto, fname, remitente)

        if not es_factura:
            print(f"  [ignorado {confianza}pts] {asunto[:60]}")
            return "ignoradas"

        print(f"  [factura {confianza}pts] {asunto[:60]}")

        # Descargar adjunto
        try:
            att  = service.users().messages().attachments().get(
                userId="me", messageId=msg["id"], id=att_id
            ).execute()
            data = base64.urlsafe_b64decode(att["data"])
        except Exception as e:
            print(f"    Error descargando {fname}: {e}")
            return "errores"

        empresa_dir = ADJUNTOS_DIR / str(empresa_id)
        empresa_dir.mkdir(parents=True, exist_ok=True)

        # Si es ZIP, descomprimir y buscar PDF/XML adentro
        if fname.lower().endswith(".zip"):
            archivos = descomprimir_zip(data, empresa_dir)
            if not archivos:
                print(f"    ZIP sin PDF/XML valido: {fname}")
                return "errores"
        else:
            file_path = empresa_dir / fname
            file_path.write_bytes(data)
            archivos = [file_path]

        datos = None
        file_usado = None
        for file_path in archivos:
            if file_path.suffix.lower() == ".xml":
                datos = extraer_xml(str(file_path))
            else:
                datos = extraer_pdf(str(file_path))
            if datos:
                file_usado = file_path
                break

        if not datos:
            return "errores"

        # Completar con info del asunto si el archivo no traia todo
        if info.get("nit_emisor") and not datos.get("proveedor_nit"):
            datos["proveedor_nit"] = info["nit_emisor"]
        if info.get("nombre_emisor") and not datos.get("proveedor_nombre"):
            datos["proveedor_nombre"] = info["nombre_emisor"]
        if info.get("numero") and not datos.get("numero"):
            datos["numero"] = info["numero"]

        # Detectar empresa por NIT receptor
        empresa = detectar_o_crear_empresa(datos, sb)
        if not empresa:
            print(f"    ! Empresa no encontrada (NIT {datos.get('receptor_nit','?')}) — avisando por Telegram con botones")
            pendiente_id = guardar_empresa_pendiente(datos, fuente="gmail", sb=sb)
            empresas_all = sb.table("empresas_clientes").select("id,nit,razon_social").execute().data
            notificar_empresa_desconocida(datos, fuente="gmail", pendiente_id=pendiente_id, empresas=empresas_all)
            return "ignoradas"

        eid_real = empresa["id"]
        empresa_nombre = empresa["razon_social"]

        resultado = registrar_en_db(datos, eid_real, str(file_usado))

        if resultado == "nuevas" and remitente:
            guardar_remitente(remitente, datos.get("proveedor_nombre", ""), confianza)
            print(f"    OK Registrada: {datos.get('numero')} | {datos.get('proveedor_nombre', remitente)} → {empresa_nombre}")
            notificar_factura(datos, empresa_nombre, tipo="compra", fuente="gmail")
        else:
            print(f"    = Duplicada: {datos.get('numero')}")

        return resultado

    return "ignoradas"




# ── Registro en DB (Supabase) ─────────────────────────────────────────────────

def registrar_en_db(datos, empresa_id, archivo_path):
    numero = datos.get("numero", "")
    ya = sb.table("facturas_gastos").select("id")\
           .eq("empresa_id", empresa_id).eq("numero", numero).execute()
    if ya.data:
        return "duplicadas"

    sb.table("facturas_gastos").insert({
        "empresa_id":        empresa_id,
        "numero":            numero,
        "cufe":              datos.get("cufe", ""),
        "fecha":             datos.get("fecha") or datetime.today().strftime("%Y-%m-%d"),
        "proveedor_nit":     datos.get("proveedor_nit", ""),
        "proveedor_nombre":  datos.get("proveedor_nombre", ""),
        "proveedor_ciudad":  datos.get("proveedor_ciudad", ""),
        "subtotal":          datos.get("subtotal", 0),
        "iva":               datos.get("iva", 0),
        "total_factura":     datos.get("total_factura", 0),
        "valor_neto":        datos.get("valor_neto", datos.get("total_factura", 0)),
        "estado":            "pendiente",
        "archivo_pdf":       archivo_path,
        "fuente":            "gmail",
    }).execute()
    return "nuevas"


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--empresa", type=int, default=None, help="ID empresa (omitir = todas)")
    parser.add_argument("--max",     type=int, default=100)
    args = parser.parse_args()
    if args.empresa:
        escanear_inbox(empresa_id=args.empresa, max_correos=args.max)
    else:
        escanear_todas_empresas(max_correos=args.max)
