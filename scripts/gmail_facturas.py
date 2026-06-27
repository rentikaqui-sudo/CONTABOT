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

import os, sys, base64, re, argparse, json, logging
from pathlib import Path
from datetime import datetime, timezone
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
    from supabase import create_client as _create_client
except ImportError:
    print("ERROR: pip install supabase")
    sys.exit(1)

# ── Rutas y configuración ─────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

import sys as _sys
_sys.path.insert(0, str(BASE_DIR / "scripts"))
from extractor import extraer_xml, extraer_pdf, descomprimir_zip, detectar_o_crear_empresa, guardar_empresa_pendiente, determinar_flujo
from telegram_notif import notificar_factura, notificar_empresa_desconocida
ADJUNTOS_DIR  = BASE_DIR / "data" / "facturas_recibidas"
TOKEN_PATH    = BASE_DIR / "data" / "gmail_token.json"
CREDS_PATH    = BASE_DIR / "data" / "gmail_credentials.json"
APRENDIZAJE   = BASE_DIR / "data" / "remitentes_facturas.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def get_sb():
    """Crea el cliente Supabase bajo demanda (no al importar el módulo)."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL y SUPABASE_SERVICE_KEY deben estar en .env")
    return _create_client(url, key)

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

def _decrypt_token(token: str) -> str:
    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key:
        return token
    try:
        from cryptography.fernet import Fernet
        f = Fernet(key.encode() if isinstance(key, str) else key)
        return f.decrypt(token.encode()).decode()
    except Exception:
        return token  # plaintext fallback


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

def get_gmail_from_supabase(empresa_id: int, sb=None):
    """Construye el servicio de Gmail usando el refresh_token guardado en Supabase."""
    if sb is None:
        sb = get_sb()
    rows = sb.table("gmail_tokens").select("*").eq("empresa_id", empresa_id).eq("activo", True).execute().data
    if not rows:
        return None, None
    t = rows[0]
    client_id, client_secret = _get_client_secrets()
    if not client_id:
        logging.error("[gmail] GOOGLE_CLIENT_ID no configurado")
        return None, None
    creds = Credentials(
        token=None,
        refresh_token=_decrypt_token(t["refresh_token"]),
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
        logging.warning("No se pudo marcar como leido: %s", e)


# ── Escaneo principal ─────────────────────────────────────────────────────────

def registrar_watch(service, empresa_id: int) -> dict:
    """Activa notificaciones Push de Gmail via Pub/Sub para esta cuenta."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT_ID", "")
    topic      = os.environ.get("PUBSUB_TOPIC_NAME", "contabot-gmail")
    topic_full = f"projects/{project_id}/topics/{topic}"
    result = service.users().watch(userId="me", body={
        "labelIds": ["INBOX"],
        "topicName": topic_full,
        "labelFilterBehavior": "INCLUDE"
    }).execute()
    _sb = get_sb()
    exp_ms = result.get("expiration", "")
    try:
        exp_iso = datetime.utcfromtimestamp(int(exp_ms) / 1000).strftime("%Y-%m-%dT%H:%M:%SZ") if exp_ms else ""
    except (ValueError, TypeError):
        exp_iso = str(exp_ms)
    _sb.table("gmail_tokens").update({
        "history_id":    str(result.get("historyId", "")),
        "watch_expires": exp_iso,
    }).eq("empresa_id", empresa_id).execute()
    logging.info("[push] Watch registrado empresa %s — expira %s", empresa_id, result.get('expiration'))
    return result

def renovar_todos_los_watches():
    """Renueva el watch de Pub/Sub para todas las cuentas activas."""
    _sb = get_sb()
    tokens = _sb.table("gmail_tokens").select("*").eq("activo", True).execute().data
    for t in tokens:
        try:
            service, _ = get_gmail_from_supabase(t["empresa_id"])
            if service:
                registrar_watch(service, t["empresa_id"])
        except Exception as e:
            logging.exception(f"[push] Error renovando watch empresa {t['empresa_id']}")

def escanear_desde_history(service, empresa_id: int, email: str, history_id: str):
    """Lee solo los mensajes nuevos desde el último historyId conocido."""
    try:
        _sb = get_sb()
        history = service.users().history().list(
            userId="me",
            startHistoryId=history_id,
            historyTypes=["messageAdded"],
            labelId="INBOX"
        ).execute()
        nuevo_history_id = str(history.get("historyId", history_id))
        _sb.table("gmail_tokens").update({"history_id": nuevo_history_id}).eq("empresa_id", empresa_id).execute()
        msg_ids = []
        for h in history.get("history", []):
            for m in h.get("messagesAdded", []):
                msg_ids.append(m["message"]["id"])
        if not msg_ids:
            logging.info("[push] %s: sin mensajes nuevos", email)
            return
        logging.info("[push] %s: %d mensajes nuevos", email, len(msg_ids))
        service_obj = service
        for mid in msg_ids:
            msg = service_obj.users().messages().get(userId="me", id=mid, format="full").execute()
            procesar_mensaje(service_obj, msg, empresa_id)
    except Exception as e:
        logging.exception(f"[push] Error history empresa {empresa_id}")

def hay_correos_nuevos(service) -> bool:
    """Consulta liviana: retorna True solo si hay no leídos con adjuntos PDF/XML/ZIP."""
    try:
        r = service.users().messages().list(
            userId="me",
            q="has:attachment is:unread (filename:pdf OR filename:xml OR filename:zip)",
            maxResults=1
        ).execute()
        return bool(r.get("messages"))
    except Exception:
        return False

def escanear_todas_empresas(max_correos=50, sb=None):
    """Escanea el Gmail de cada cliente solo si tiene correos no leídos relevantes."""
    if sb is None:
        sb = get_sb()
    tokens = sb.table("gmail_tokens").select("empresa_id,email").eq("activo", True).execute().data
    if not tokens:
        logging.info("[gmail] No hay cuentas de Gmail conectadas.")
        return
    for t in tokens:
        eid   = t["empresa_id"]
        email = t["email"]
        try:
            service, _ = get_gmail_from_supabase(eid)
            if not service:
                logging.warning("[gmail] Sin token para empresa %s", eid)
                continue
            if not hay_correos_nuevos(service):
                logging.info("[gmail] %s — sin correos nuevos, omitiendo", email)
                continue
            logging.info("[gmail] Escaneando %s (empresa %s)...", email, eid)
            escanear_inbox(empresa_id=eid, max_correos=max_correos, service=service)
        except Exception as e:
            logging.exception(f"[gmail] Error empresa {eid} ({email})")

def escanear_inbox(empresa_id, max_correos=100, service=None):
    if service is None:
        service = get_gmail()

    # Query amplia — el filtro inteligente lo hace puntaje_es_factura()
    query = "has:attachment is:unread (filename:pdf OR filename:xml OR filename:zip)"
    logging.info("Buscando en Gmail (máx %d correos)...", max_correos)

    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_correos
    ).execute()

    mensajes = result.get("messages", [])
    logging.info("Correos con adjuntos encontrados: %d", len(mensajes))

    stats = {"nuevas": 0, "duplicadas": 0, "ignoradas": 0, "errores": 0}

    for ref in mensajes:
        msg = service.users().messages().get(
            userId="me", id=ref["id"], format="full"
        ).execute()
        resultado = procesar_mensaje(service, msg, empresa_id)
        stats[resultado] = stats.get(resultado, 0) + 1
        if resultado in ("nuevas", "duplicadas"):
            marcar_leido(service, ref["id"])

    logging.info("Resultado: nuevas=%d duplicadas=%d ignoradas=%d errores=%d",
                 stats['nuevas'], stats['duplicadas'], stats['ignoradas'], stats['errores'])
    return stats


# ── Procesamiento de un mensaje ───────────────────────────────────────────────

def _descargar_adjunto(service, msg_id: str, att_id: str, fname: str, empresa_dir: Path):
    """Descarga adjunto de Gmail, guarda en disco. Retorna lista de paths o None si falla."""
    att  = service.users().messages().attachments().get(userId="me", messageId=msg_id, id=att_id).execute()
    data = base64.urlsafe_b64decode(att["data"])
    empresa_dir.mkdir(parents=True, exist_ok=True)
    if fname.lower().endswith(".zip"):
        archivos = descomprimir_zip(data, empresa_dir)
        if not archivos:
            logging.warning("ZIP sin PDF/XML valido: %s", fname)
            return None
        return archivos
    file_path = empresa_dir / fname
    file_path.write_bytes(data)
    return [file_path]


def _extraer_datos_adjunto(archivos):
    """Intenta extraer datos DIAN de la lista de archivos. Retorna (datos, file_usado)."""
    for file_path in archivos:
        datos = extraer_xml(str(file_path)) if file_path.suffix.lower() == ".xml" else extraer_pdf(str(file_path))
        if datos:
            return datos, file_path
    return None, None


def _enriquecer_datos(datos: dict, info: dict) -> dict:
    """Completa campos faltantes con info extraída del asunto del correo."""
    for campo_datos, campo_info in [("proveedor_nit", "nit_emisor"), ("proveedor_nombre", "nombre_emisor"), ("numero", "numero")]:
        if info.get(campo_info) and not datos.get(campo_datos):
            datos[campo_datos] = info[campo_info]
    return datos


def procesar_mensaje(service, msg, empresa_id):
    headers   = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    asunto    = headers.get("Subject", "")
    remitente = re.search(r"[\w\.\-]+@[\w\.\-]+", headers.get("From", ""))
    remitente = remitente.group(0).lower() if remitente else ""

    for part in msg["payload"].get("parts", []):
        fname  = part.get("filename", "")
        att_id = part.get("body", {}).get("attachmentId")
        if not fname or not att_id or not fname.lower().endswith((".pdf", ".xml", ".zip")):
            continue

        es_factura, confianza, info = puntaje_es_factura(asunto, fname, remitente)
        if not es_factura:
            logging.debug("[ignorado %dpts] %s", confianza, asunto[:60])
            continue
        logging.info("[factura %dpts] %s", confianza, asunto[:60])

        try:
            archivos = _descargar_adjunto(service, msg["id"], att_id, fname, ADJUNTOS_DIR / str(empresa_id))
        except Exception:
            logging.exception("Error descargando %s", fname)
            continue
        if not archivos:
            continue

        datos, file_usado = _extraer_datos_adjunto(archivos)
        if not datos:
            continue
        datos = _enriquecer_datos(datos, info)

        _sb = get_sb()
        empresa = detectar_o_crear_empresa(datos, _sb)
        if not empresa:
            logging.warning("Empresa no encontrada (NIT %s) — avisando por Telegram", datos.get("receptor_nit", "?"))
            pendiente_id = guardar_empresa_pendiente(datos, fuente="gmail", sb=_sb)
            empresas_all = _sb.table("empresas_clientes").select("id,nit,razon_social").execute().data
            notificar_empresa_desconocida(datos, fuente="gmail", pendiente_id=pendiente_id, empresas=empresas_all)
            return "ignoradas"

        resultado = registrar_en_db(datos, empresa["id"], empresa["nit"], str(file_usado))
        if resultado == "nuevas" and remitente:
            flujo = determinar_flujo(datos, empresa["nit"])
            guardar_remitente(remitente, datos.get("proveedor_nombre", ""), confianza)
            logging.info("[%s] Registrada: %s | %s → %s", flujo, datos.get("numero"), datos.get("proveedor_nombre", remitente), empresa["razon_social"])
            notificar_factura(datos, empresa["razon_social"], tipo=flujo, fuente="gmail")
        else:
            logging.info("Duplicada: %s", datos.get("numero"))
        return resultado

    return "ignoradas"




# ── Registro en DB (Supabase) ─────────────────────────────────────────────────

def registrar_en_db(datos, empresa_id, empresa_nit, archivo_path, sb=None):
    if sb is None:
        sb = get_sb()
    from extractor import subir_a_storage, guardar_factura
    fecha = datos.get("fecha") or datetime.today().strftime("%Y-%m-%d")
    storage_url = subir_a_storage(archivo_path, empresa_id, datos.get("numero",""), fecha, sb)
    flujo, resultado = guardar_factura(datos, empresa_id, empresa_nit,
                                       storage_url or archivo_path, "gmail", sb)
    return "nuevas" if resultado == "nueva" else "duplicadas"


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
