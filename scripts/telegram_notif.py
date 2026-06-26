"""
telegram_notif.py — Notificaciones ContaBot a Telegram.
"""

import os
import urllib.request
import json


def _send(token: str, chat_id: str, texto: str):
    payload = json.dumps({
        "chat_id":    chat_id,
        "text":       texto,
        "parse_mode": "Markdown",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"Telegram: no se pudo enviar: {e}")


def notificar_factura(datos: dict, empresa_nombre: str, tipo: str = "compra", fuente: str = ""):
    """
    tipo:   "compra" (factura recibida) o "venta" (factura emitida)
    fuente: "gmail", "upload", "manual"
    """
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
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


def notificar_empresa_desconocida(datos: dict, fuente: str = "gmail", pendiente_id: str = None, empresas: list = None):
    """
    Avisa cuando llega una factura con NIT receptor desconocido.
    Muestra botones con todas las empresas registradas para que Eduardo seleccione a cuál pertenece.
    """
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return

    nit    = datos.get("receptor_nit") or "desconocido"
    nombre = datos.get("receptor_nombre") or ""
    prov   = datos.get("proveedor_nombre", "")
    num    = datos.get("numero", "—")
    fuente_label = {"gmail": "📧 correo", "upload": "⬆️ subida"}.get(fuente, fuente)

    def fmt(v):
        try: return f"${int(v or 0):,}".replace(",", ".")
        except: return "$0"

    total = fmt(datos.get("total_factura"))

    texto = (
        f"⚠️ *No reconocí el receptor de esta factura*\n\n"
        f"📄 Factura N° {num} de *{prov or 'proveedor desconocido'}* — {total}\n"
        f"🔢 NIT/CC en factura: `{nit}`\n"
        f"Via: {fuente_label}\n\n"
        f"*¿A cuál de tus clientes pertenece?*"
    )

    payload = {
        "chat_id":    chat_id,
        "text":       texto,
        "parse_mode": "Markdown",
    }

    if pendiente_id:
        teclado = []
        # Un botón por empresa registrada
        if empresas:
            for e in empresas:
                teclado.append([{
                    "text": f"📌 {e['razon_social']}",
                    "callback_data": f"asignar_empresa:{pendiente_id}:{e['id']}"
                }])
        # Botón ignorar al final
        teclado.append([{
            "text": "❌ No es de ningún cliente, ignorar",
            "callback_data": f"ignorar_empresa:{pendiente_id}"
        }])
        payload["reply_markup"] = json.dumps({"inline_keyboard": teclado})

    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"Telegram: no se pudo enviar: {e}")
