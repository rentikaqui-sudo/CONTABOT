"""
telegram_notif.py — Notificaciones ContaBot a Telegram.
"""

import os
import urllib.request
import json


def _get_chat_id(sb=None, contador_id=None) -> str:
    """Retorna el telegram_chat_id del contador; fallback a la variable de entorno global."""
    if sb and contador_id:
        try:
            rows = sb.table("contadores").select("telegram_chat_id").eq("id", contador_id).execute().data
            if rows and rows[0].get("telegram_chat_id"):
                return rows[0]["telegram_chat_id"]
        except Exception:
            pass
    return os.environ.get("TELEGRAM_CHAT_ID", "")


def _send(token: str, chat_id: str, texto: str, reply_markup=None):
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"Telegram: no se pudo enviar: {e}")


def notificar_factura(datos: dict, empresa_nombre: str, tipo: str = "compra",
                      fuente: str = "", sb=None, contador_id=None):
    """
    tipo:   "compra" (factura recibida) o "venta" (factura emitida)
    fuente: "gmail", "upload", "manual"
    """
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = _get_chat_id(sb, contador_id)
    if not token or not chat_id:
        return

    icono = "📥" if tipo == "compra" else "📤"
    tipo_label = "Factura de compra" if tipo == "compra" else "Factura de venta"
    fuente_label = {
        "gmail":  "📧 Correo automático",
        "upload": "⬆️ Subida manual",
        "manual": "✏️ Ingreso manual",
    }.get(fuente, "ContaBot")

    contraparte = datos.get("proveedor_nombre") or datos.get("cliente_nombre") or "Desconocido"
    nit_cp = datos.get("proveedor_nit") or datos.get("cliente_nit") or ""
    numero = datos.get("numero", "—")
    fecha  = datos.get("fecha", "—")

    def fmt(v): return f"${int(v or 0):,}".replace(",", ".")

    texto = (
        f"{icono} *{tipo_label} registrada*\n"
        f"👤 Cliente: *{empresa_nombre}*\n"
        f"🏢 {'Proveedor' if tipo == 'compra' else 'Cliente'}: {contraparte}"
        + (f" (NIT {nit_cp})" if nit_cp else "") + "\n"
        f"📄 Factura N° {numero} | Fecha: {fecha}\n"
        f"💰 Total: {fmt(datos.get('total_factura'))} | IVA: {fmt(datos.get('iva'))}\n"
        f"📍 Procedencia: {fuente_label}"
    )
    _send(token, chat_id, texto)


def notificar_empresa_desconocida(datos: dict, fuente: str = "gmail",
                                   pendiente_id: str = None, empresas: list = None,
                                   sb=None, contador_id=None):
    """
    Avisa cuando llega una factura con NIT receptor desconocido.
    Usa reply_keyboard (teclado nativo) para selección — más confiable que inline buttons.
    Lógica de cola: solo envía el teclado si no hay otra factura pendiente esperando
    respuesta del usuario. Las demás quedan en DB y se preguntan automáticamente
    después de que el usuario responda la anterior.
    """
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = _get_chat_id(sb, contador_id)
    if not token or not chat_id:
        return

    # Cola: contar cuántas pendientes hay para este contador en Supabase.
    # Si hay más de 1 (esta + otras anteriores), no enviar teclado — ya hay una en curso.
    if sb and contador_id and pendiente_id:
        try:
            total_pendientes = sb.table("empresas_pendientes").select("id", count="exact") \
                .eq("contador_id", contador_id).execute().count
            if total_pendientes is not None and total_pendientes > 1:
                return  # Hay otra pregunta activa; esta se enviará después
        except Exception:
            pass

    _enviar_pregunta_empresa(token, chat_id, datos, fuente, empresas)


def _enviar_pregunta_empresa(token: str, chat_id: str, datos: dict,
                              fuente: str = "gmail", empresas: list = None):
    """Envía el mensaje con reply_keyboard para asignar empresa a una factura pendiente."""
    nit   = datos.get("receptor_nit") or "desconocido"
    prov  = datos.get("proveedor_nombre") or datos.get("cliente_nombre") or "proveedor desconocido"
    num   = datos.get("numero", "—")
    fuente_label = {"gmail": "📧 correo", "upload": "⬆️ subida"}.get(fuente, fuente)

    def fmt(v):
        try: return f"${int(v or 0):,}".replace(",", ".")
        except: return "$0"

    texto = (
        f"⚠️ *No reconocí el receptor de esta factura*\n\n"
        f"📄 Factura N° {num} de *{prov}* — {fmt(datos.get('total_factura'))}\n"
        f"🔢 NIT/CC en factura: `{nit}`\n"
        f"Via: {fuente_label}\n\n"
        f"*¿A cuál de tus clientes pertenece?*"
    )

    opciones = [e["razon_social"] for e in (empresas or [])]
    opciones.append("❌ No es de ningún cliente, ignorar")

    reply_markup = json.dumps({
        "keyboard": [[{"text": op}] for op in opciones],
        "one_time_keyboard": True,
        "resize_keyboard": True,
    })
    _send(token, chat_id, texto, reply_markup=reply_markup)
