"""
ContaBot — Flask API multi-empresa
El contador gestiona 6 empresas clientes desde un solo panel.
Data layer: Supabase (service_role key, bypasses RLS)
"""

import os, json, functools, re, sys
from datetime import date, timedelta
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, request, session, redirect
from dotenv import load_dotenv
from supabase import create_client, Client

# ── Configuración ─────────────────────────────────────────────────────────────

BASE_DIR     = os.path.dirname(os.path.dirname(__file__))
UI_DIR       = os.path.join(BASE_DIR, "ui")
SCRIPTS_DIR  = os.path.join(BASE_DIR, "scripts")
FACTURAS_DIR = Path(BASE_DIR) / "data" / "facturas_recibidas"

load_dotenv(os.path.join(BASE_DIR, ".env"))

sys.path.insert(0, SCRIPTS_DIR)
from extractor import extraer_xml, extraer_pdf, descomprimir_zip, detectar_empresa, detectar_o_crear_empresa, guardar_empresa_pendiente
from telegram_notif import notificar_factura, notificar_empresa_desconocida
from calendario import todas_las_obligaciones, obligaciones_proximas

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__, static_folder=UI_DIR)
app.secret_key = "contabot-demo-2026-key-x7f"


# ── Auth helper ───────────────────────────────────────────────────────────────

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "No autorizado", "redirect": "/login"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Páginas ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if not session.get("logged_in"):
        return redirect("/login")
    return send_from_directory(UI_DIR, "index.html")

@app.route("/bienvenida")
def bienvenida():
    return send_from_directory(UI_DIR, "bienvenida.html")

@app.route("/login")
def login_page():
    if session.get("logged_in"):
        return redirect("/")
    return send_from_directory(UI_DIR, "login.html")

@app.route("/<path:f>")
def static_files(f):
    return send_from_directory(UI_DIR, f)


# ── Auth ─────────────────────────────────────────────────────────────────────

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    if data.get("usuario") == "contador" and data.get("password") == "contabot2026":
        session["logged_in"] = True
        session["usuario"] = "contador"
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Usuario o contraseña incorrectos"}), 401

@app.route("/api/logout")
def api_logout():
    session.clear()
    return redirect("/login")


# ── Vista general: todas las empresas del contador ───────────────────────────

@app.route("/api/empresas")
@login_required
def empresas():
    empresas_rows = sb.table("empresas_clientes").select("*").order("id").execute().data
    resultado = []

    for e in empresas_rows:
        eid = e["id"]

        ventas_rows = sb.table("facturas_venta").select("valor_neto,estado").eq("empresa_id", eid).execute().data
        gastos_rows = sb.table("facturas_gastos").select("valor_neto,estado").eq("empresa_id", eid).execute().data

        # Aggregate ventas in Python
        v_n           = len(ventas_rows)
        v_neto        = sum(r["valor_neto"] or 0 for r in ventas_rows)
        v_por_cobrar  = sum(r["valor_neto"] or 0 for r in ventas_rows if r["estado"] == "PENDIENTE")
        v_vencido     = sum(r["valor_neto"] or 0 for r in ventas_rows if "VENCIDA" in str(r["estado"]).upper())
        v_cobrado     = sum(r["valor_neto"] or 0 for r in ventas_rows if r["estado"] == "PAGADA")
        v_n_vencidas  = sum(1 for r in ventas_rows if "VENCIDA" in str(r["estado"]).upper())
        v_n_por_vencer= sum(1 for r in ventas_rows if r["estado"] == "POR_VENCER")

        # Aggregate gastos in Python
        g_n          = len(gastos_rows)
        g_neto       = sum(r["valor_neto"] or 0 for r in gastos_rows)
        g_por_pagar  = sum(r["valor_neto"] or 0 for r in gastos_rows if r["estado"] == "PENDIENTE")
        g_pagado     = sum(r["valor_neto"] or 0 for r in gastos_rows if r["estado"] == "PAGADA")

        alertas  = v_n_vencidas + v_n_por_vencer
        semaforo = "verde"
        if v_n_vencidas >= 2:
            semaforo = "rojo"
        elif alertas > 0:
            semaforo = "amarillo"

        resultado.append({
            "id":           e["id"],
            "razon_social": e["razon_social"],
            "nit":          e["nit"],
            "sector":       e["sector"],
            "ciudad":       e["ciudad"],
            "contacto":     e["contacto"],
            "color":        e["color"],
            "icono":        e["icono"],
            "semaforo":     semaforo,
            "ventas": {
                "n":            v_n,
                "neto":         round(v_neto),
                "por_cobrar":   round(v_por_cobrar),
                "vencido":      round(v_vencido),
                "cobrado":      round(v_cobrado),
                "n_vencidas":   v_n_vencidas,
                "n_por_vencer": v_n_por_vencer,
            },
            "gastos": {
                "n":        g_n,
                "neto":     round(g_neto),
                "por_pagar":round(g_por_pagar),
                "pagado":   round(g_pagado),
            },
            "alertas": alertas,
        })

    return jsonify(resultado)


@app.route("/api/empresas", methods=["POST"])
@login_required
def crear_empresa():
    body = request.get_json()
    nit          = (body.get("nit") or "").strip()
    razon_social = (body.get("razon_social") or "").strip()
    ciudad       = (body.get("ciudad") or "").strip()
    sector       = (body.get("sector") or "General").strip()
    contacto     = (body.get("contacto") or "").strip()

    if not nit or not razon_social:
        return jsonify({"ok": False, "error": "NIT y razón social son obligatorios"}), 400

    # Verificar duplicado
    existe = sb.table("empresas_clientes").select("id").eq("nit", nit).execute().data
    if existe:
        return jsonify({"ok": False, "error": f"Ya existe una empresa con NIT {nit}"}), 409

    # Colores e iconos rotativos
    COLORES = ["#6366f1","#10b981","#f59e0b","#ef4444","#3b82f6","#8b5cf6","#ec4899","#14b8a6"]
    ICONOS  = ["🏢","🏭","🛒","🏗️","💊","🚛","🍽️","📦","⚙️","🏬"]
    count   = len(sb.table("empresas_clientes").select("id").execute().data)
    color   = COLORES[count % len(COLORES)]
    icono   = ICONOS[count % len(ICONOS)]

    regimen = (body.get("regimen") or "Juridica").strip()

    row = sb.table("empresas_clientes").insert({
        "nit":          nit,
        "razon_social": razon_social,
        "ciudad":       ciudad,
        "sector":       sector,
        "contacto":     contacto,
        "color":        color,
        "icono":        icono,
        "regimen":      regimen,
    }).execute().data

    return jsonify({"ok": True, "empresa": row[0] if row else {}})


@app.route("/api/empresa/<int:eid>", methods=["PUT"])
@login_required
def editar_empresa(eid):
    body = request.get_json() or {}
    campos = {}
    for k in ("nit", "razon_social", "ciudad", "sector", "contacto", "regimen"):
        v = body.get(k)
        if v is not None:
            campos[k] = str(v).strip()
    if not campos:
        return jsonify({"ok": False, "error": "Nada que actualizar"}), 400
    row = sb.table("empresas_clientes").update(campos).eq("id", eid).execute().data
    return jsonify({"ok": True, "empresa": row[0] if row else {}})


# ── Resumen consolidado del contador ─────────────────────────────────────────

@app.route("/api/resumen")
@login_required
def resumen():
    ventas_rows = sb.table("facturas_venta").select("valor_neto,estado").execute().data
    gastos_rows = sb.table("facturas_gastos").select("valor_neto,estado").execute().data
    n_empresas  = len(sb.table("empresas_clientes").select("id").execute().data)

    v_neto        = sum(r["valor_neto"] or 0 for r in ventas_rows)
    v_por_cobrar  = sum(r["valor_neto"] or 0 for r in ventas_rows if r["estado"] == "PENDIENTE")
    v_vencido     = sum(r["valor_neto"] or 0 for r in ventas_rows if "VENCIDA" in str(r["estado"]).upper())
    v_n_vencidas  = sum(1 for r in ventas_rows if "VENCIDA" in str(r["estado"]).upper())
    v_n_por_vencer= sum(1 for r in ventas_rows if r["estado"] == "POR_VENCER")

    g_neto       = sum(r["valor_neto"] or 0 for r in gastos_rows)
    g_por_pagar  = sum(r["valor_neto"] or 0 for r in gastos_rows if r["estado"] == "PENDIENTE")

    return jsonify({
        "n_empresas":      n_empresas,
        "total_ventas":    round(v_neto),
        "por_cobrar":      round(v_por_cobrar),
        "cartera_vencida": round(v_vencido),
        "n_vencidas":      v_n_vencidas,
        "n_por_vencer":    v_n_por_vencer,
        "total_gastos":    round(g_neto),
        "por_pagar":       round(g_por_pagar),
        "total_facturas":  len(ventas_rows) + len(gastos_rows),
    })


# ── Detalle de una empresa ────────────────────────────────────────────────────

@app.route("/api/empresa/<int:eid>/dashboard")
@login_required
def empresa_dashboard(eid):
    e_rows = sb.table("empresas_clientes").select("*").eq("id", eid).execute().data
    if not e_rows:
        return jsonify({"error": "Empresa no encontrada"}), 404
    e = e_rows[0]

    ventas_rows = sb.table("facturas_venta").select("valor_neto,estado,retefuente,reteiva,reteica").eq("empresa_id", eid).execute().data
    gastos_rows = sb.table("facturas_gastos").select("valor_neto,estado,retefuente,reteiva,reteica").eq("empresa_id", eid).execute().data

    v_n         = len(ventas_rows)
    v_neto      = sum(r["valor_neto"] or 0 for r in ventas_rows)
    v_por_cobrar= sum(r["valor_neto"] or 0 for r in ventas_rows if r["estado"] == "PENDIENTE")
    v_vencido   = sum(r["valor_neto"] or 0 for r in ventas_rows if "VENCIDA" in str(r["estado"]).upper())
    v_cobrado   = sum(r["valor_neto"] or 0 for r in ventas_rows if r["estado"] == "PAGADA")

    g_n         = len(gastos_rows)
    g_neto      = sum(r["valor_neto"] or 0 for r in gastos_rows)
    g_por_pagar = sum(r["valor_neto"] or 0 for r in gastos_rows if r["estado"] == "PENDIENTE")
    g_pagado    = sum(r["valor_neto"] or 0 for r in gastos_rows if r["estado"] == "PAGADA")

    ret_v_rf = sum(r["retefuente"] or 0 for r in ventas_rows)
    ret_v_ri = sum(r["reteiva"]    or 0 for r in ventas_rows)
    ret_v_rc = sum(r["reteica"]    or 0 for r in ventas_rows)

    ret_g_rf = sum(r["retefuente"] or 0 for r in gastos_rows)
    ret_g_ri = sum(r["reteiva"]    or 0 for r in gastos_rows)
    ret_g_rc = sum(r["reteica"]    or 0 for r in gastos_rows)

    return jsonify({
        "empresa": e,
        "ventas": {
            "n":          v_n,
            "neto":       round(v_neto),
            "por_cobrar": round(v_por_cobrar),
            "vencido":    round(v_vencido),
            "cobrado":    round(v_cobrado),
        },
        "gastos": {
            "n":        g_n,
            "neto":     round(g_neto),
            "por_pagar":round(g_por_pagar),
            "pagado":   round(g_pagado),
        },
        "retenciones_ventas": {
            "retefuente": round(ret_v_rf),
            "reteiva":    round(ret_v_ri),
            "reteica":    round(ret_v_rc),
        },
        "retenciones_gastos": {
            "retefuente": round(ret_g_rf),
            "reteiva":    round(ret_g_ri),
            "reteica":    round(ret_g_rc),
        },
    })


@app.route("/api/empresa/<int:eid>/facturas/venta")
@login_required
def empresa_ventas(eid):
    rows = (
        sb.table("facturas_venta")
        .select("numero,fecha,fecha_vencimiento,cliente_nombre,cliente_ciudad,"
                "gran_contribuyente,subtotal,iva,retefuente,reteiva,reteica,"
                "total_factura,valor_neto,estado")
        .eq("empresa_id", eid)
        .order("fecha", desc=True)
        .execute().data
    )
    return jsonify(rows)


@app.route("/api/empresa/<int:eid>/facturas/gastos")
@login_required
def empresa_gastos(eid):
    rows = (
        sb.table("facturas_gastos")
        .select("numero,fecha,fecha_vencimiento,proveedor_nombre,proveedor_ciudad,"
                "categoria,subtotal,iva,retefuente,reteiva,reteica,"
                "total_factura,valor_neto,estado")
        .eq("empresa_id", eid)
        .order("fecha", desc=True)
        .execute().data
    )
    return jsonify(rows)


@app.route("/api/empresa/<int:eid>/alertas")
@login_required
def empresa_alertas(eid):
    e_rows = sb.table("empresas_clientes").select("razon_social").eq("id", eid).execute().data
    if not e_rows:
        return jsonify([])
    e = e_rows[0]

    rows = (
        sb.table("facturas_venta")
        .select("numero,cliente_nombre,cliente_ciudad,valor_neto,fecha_vencimiento,estado")
        .eq("empresa_id", eid)
        .order("fecha_vencimiento")
        .execute().data
    )
    # Filter: estado LIKE 'VENCIDA%' OR estado='POR_VENCER'
    rows = [r for r in rows if "VENCIDA" in str(r["estado"]).upper() or r["estado"] == "POR_VENCER"]

    result = []
    for d in rows:
        es_vencida = "VENCIDA" in d["estado"].upper()
        nombre_corto = d["cliente_nombre"].split()
        d["email_preview"] = (
            f"Estimado(a) {' '.join(nombre_corto[:2])},\n\n"
            f"Le recordamos que la factura {d['numero']} de {e['razon_social']}\n"
            f"por valor de ${d['valor_neto']:,.0f} COP se encuentra "
            f"{'VENCIDA' if es_vencida else 'proxima a vencer'}"
            f" (vencimiento: {d['fecha_vencimiento']}).\n\n"
            f"Le agradecemos gestionar el pago a la mayor brevedad posible.\n\n"
            f"Atentamente,\nEstudio Contable Aristizabal & Asociados\n"
            f"Tel: 315-890-4321 | info@contablearistizabal.com.co"
        ).replace(",", ".")
        result.append(d)
    return jsonify(result)


# ── Alertas globales (todas las empresas) ────────────────────────────────────

@app.route("/api/alertas/global")
@login_required
def alertas_global():
    # Fetch facturas with alert states
    fv_rows = (
        sb.table("facturas_venta")
        .select("numero,cliente_nombre,valor_neto,fecha_vencimiento,estado,empresa_id")
        .order("fecha_vencimiento")
        .execute().data
    )
    fv_rows = [r for r in fv_rows if "VENCIDA" in str(r["estado"]).upper() or r["estado"] == "POR_VENCER"]

    # Fetch all empresas for join
    empresas_map = {
        e["id"]: e
        for e in sb.table("empresas_clientes").select("id,razon_social,color").execute().data
    }

    result = []
    for r in fv_rows:
        emp = empresas_map.get(r["empresa_id"], {})
        result.append({
            "numero":          r["numero"],
            "cliente_nombre":  r["cliente_nombre"],
            "valor_neto":      r["valor_neto"],
            "fecha_vencimiento":r["fecha_vencimiento"],
            "estado":          r["estado"],
            "empresa_nombre":  emp.get("razon_social", ""),
            "empresa_color":   emp.get("color", ""),
            "empresa_id":      r["empresa_id"],
        })
    return jsonify(result)


# ── Retenciones por cliente (para una empresa dada) ───────────────────────────

@app.route("/api/empresa/<int:eid>/retenciones-por-cliente")
@login_required
def retenciones_por_cliente(eid):
    rows = (
        sb.table("facturas_venta")
        .select("cliente_nit,cliente_nombre,cliente_ciudad,retefuente,reteiva,reteica,valor_neto")
        .eq("empresa_id", eid)
        .execute().data
    )

    # GROUP BY cliente_nit in Python
    grupos = {}
    for r in rows:
        key = r["cliente_nit"]
        if key not in grupos:
            grupos[key] = {
                "cliente_nombre":  r["cliente_nombre"],
                "cliente_ciudad":  r["cliente_ciudad"],
                "n_facturas":      0,
                "retefuente":      0,
                "reteiva":         0,
                "reteica":         0,
                "valor_neto":      0,
            }
        g = grupos[key]
        g["n_facturas"] += 1
        g["retefuente"] += r["retefuente"] or 0
        g["reteiva"]    += r["reteiva"]    or 0
        g["reteica"]    += r["reteica"]    or 0
        g["valor_neto"] += r["valor_neto"] or 0

    result = []
    for g in grupos.values():
        g["total_ret"] = g["retefuente"] + g["reteiva"] + g["reteica"]
        result.append(g)

    result.sort(key=lambda x: x["total_ret"], reverse=True)
    return jsonify(result)


# ── Factura manual (papel) ────────────────────────────────────────────────────

@app.route("/api/factura-manual", methods=["POST"])
@login_required
def factura_manual():
    data = request.get_json()

    fecha     = data.get("fecha", date.today().isoformat())
    dias      = int(data.get("dias_pago", 30))
    fecha_vto = (date.fromisoformat(fecha) + timedelta(days=dias)).isoformat()

    hoy      = date.today()
    vto_date = date.fromisoformat(fecha_vto)
    if dias == 0:
        estado = "PAGADA"
    elif vto_date < hoy:
        estado = f"VENCIDA ({(hoy - vto_date).days} dias)"
    elif (vto_date - hoy).days <= 7:
        estado = "POR_VENCER"
    else:
        estado = "PENDIENTE"

    tipo = data.get("tipo", "gasto")

    try:
        if tipo == "gasto":
            sb.table("facturas_gastos").upsert({
                "empresa_id":       data["empresa_id"],
                "numero":           data["numero"],
                "cufe":             "MANUAL-" + data["numero"],
                "fecha":            fecha,
                "fecha_vencimiento":fecha_vto,
                "proveedor_nit":    data.get("tercero_nit", ""),
                "proveedor_nombre": data.get("tercero_nombre", ""),
                "proveedor_ciudad": "Manual",
                "categoria":        data.get("categoria", "insumos"),
                "subtotal":         data["subtotal"],
                "iva":              data["iva"],
                "retefuente":       data["retefuente"],
                "reteiva":          data["reteiva"],
                "reteica":          data["reteica"],
                "total_factura":    data["total_factura"],
                "valor_neto":       data["valor_neto"],
                "estado":           estado,
                "archivo_pdf":      "",
            }, on_conflict="empresa_id,numero").execute()
        else:
            sb.table("facturas_venta").upsert({
                "empresa_id":       data["empresa_id"],
                "numero":           data["numero"],
                "cufe":             "MANUAL-" + data["numero"],
                "fecha":            fecha,
                "fecha_vencimiento":fecha_vto,
                "cliente_nit":      data.get("tercero_nit", ""),
                "cliente_nombre":   data.get("tercero_nombre", ""),
                "cliente_ciudad":   "Manual",
                "gran_contribuyente":0,
                "subtotal":         data["subtotal"],
                "iva":              data["iva"],
                "retefuente":       data["retefuente"],
                "reteiva":          data["reteiva"],
                "reteica":          data["reteica"],
                "total_factura":    data["total_factura"],
                "valor_neto":       data["valor_neto"],
                "estado":           estado,
                "archivo_pdf":      "",
            }, on_conflict="empresa_id,numero").execute()
        return jsonify({"ok": True})
    except Exception as ex:
        return jsonify({"ok": False, "error": str(ex)}), 400


# ── Procesar imagen de factura (QR / OCR) ────────────────────────────────────

@app.route("/api/procesar-imagen", methods=["POST"])
@login_required
def procesar_imagen():
    if "imagen" not in request.files:
        return jsonify({"ok": False, "error": "No se recibió imagen"}), 400

    archivo   = request.files["imagen"]
    img_bytes = archivo.read()
    nombre    = archivo.filename or "imagen"

    resultado = {"ok": True, "metodo": None, "datos": {}, "raw": "", "archivo": nombre}

    try:
        import cv2
        import numpy as np
    except ImportError:
        return jsonify({
            "ok": False,
            "error": "Falta opencv-python. Ejecute: pip install opencv-python pillow"
        }), 500

    nparr = np.frombuffer(img_bytes, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return jsonify({"ok": False, "error": "No se pudo leer la imagen. Verifique el formato (JPG, PNG, etc.)"}), 400

    # ── Intentar leer QR ──────────────────────────────────────────────────────
    detector = cv2.QRCodeDetector()
    qr_data, bbox, _ = detector.detectAndDecode(img)

    if qr_data:
        resultado["metodo"] = "qr"
        resultado["raw"]    = qr_data
        resultado["datos"]  = _parse_dian_qr(qr_data)
        return jsonify(resultado)

    # ── Intentar OCR ─────────────────────────────────────────────────────────
    try:
        import pytesseract
        from PIL import Image as PILImage
        import io

        pil_img = PILImage.open(io.BytesIO(img_bytes))
        texto   = pytesseract.image_to_string(pil_img, lang="spa+eng")
        resultado["metodo"] = "ocr"
        resultado["raw"]    = texto
        resultado["datos"]  = _parse_ocr_texto(texto)
    except ImportError:
        resultado["metodo"] = "sin_ocr"
        resultado["datos"]  = {
            "confiabilidad": "N/A",
            "fuente": "No se encontró QR y pytesseract no está instalado",
        }
        resultado["mensaje"] = "No se detectó código QR en la imagen. Instale pytesseract + Tesseract para OCR."
    except Exception as e:
        resultado["metodo"] = "error_ocr"
        resultado["datos"]  = {"fuente": "Error en OCR", "confiabilidad": "N/A"}
        resultado["mensaje"] = f"No se pudo extraer texto: {str(e)}"

    return jsonify(resultado)


def _parse_dian_qr(qr_text):
    datos = {"tipo": "url_dian", "url": qr_text}

    cufe = re.search(r'documentkey=([a-f0-9]{96})', qr_text, re.IGNORECASE)
    if cufe:
        datos["cufe"]       = cufe.group(1)
        datos["cufe_corto"] = cufe.group(1)[:16] + "..." + cufe.group(1)[-8:]

    datos["fuente"]        = "QR de factura electrónica DIAN"
    datos["confiabilidad"] = "Alta — datos directamente del portal DIAN"
    return datos


def _parse_ocr_texto(texto):
    datos = {}

    m = re.search(r'NIT[:\s.]*([0-9.]{7,12}[-–]?\d)', texto, re.IGNORECASE)
    if m:
        datos["nit"] = m.group(1).strip()

    m = re.search(r'TOTAL[:\s]*\$?\s*([\d.,]+)', texto, re.IGNORECASE)
    if m:
        datos["total_texto"] = m.group(1)
        datos["total"]       = int(re.sub(r'[.,]', '', m.group(1))[:12])

    m = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4}|\d{4}[/-]\d{2}[/-]\d{2})', texto)
    if m:
        datos["fecha"] = m.group(1)

    m = re.search(r'(?:factura|FV|FC|FE|N[°º])[:\s#-]*([A-Z0-9-]{3,20})', texto, re.IGNORECASE)
    if m:
        datos["numero"] = m.group(1).strip()

    m = re.search(r'CUFE[:\s]*([a-f0-9]{32,})', texto, re.IGNORECASE)
    if m:
        datos["cufe"] = m.group(1)[:96]

    datos["fuente"]        = "OCR — reconocimiento óptico de texto"
    datos["confiabilidad"] = "Media — verificar valores antes de guardar"
    return datos


# ── Informe mensual PDF ────────────────────────────────────────────────────────

@app.route("/api/empresa/<int:eid>/informe-pdf")
@login_required
def informe_pdf(eid):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer, HRFlowable)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from flask import make_response
    import io

    e_rows = sb.table("empresas_clientes").select("*").eq("id", eid).execute().data
    if not e_rows:
        return jsonify({"error": "Empresa no encontrada"}), 404
    e = e_rows[0]

    vs = (
        sb.table("facturas_venta")
        .select("numero,fecha,cliente_nombre,subtotal,iva,retefuente,reteiva,reteica,"
                "total_factura,valor_neto,estado")
        .eq("empresa_id", eid)
        .order("fecha")
        .execute().data
    )
    gs = (
        sb.table("facturas_gastos")
        .select("numero,fecha,proveedor_nombre,categoria,subtotal,iva,retefuente,reteiva,reteica,"
                "total_factura,valor_neto,estado")
        .eq("empresa_id", eid)
        .order("fecha")
        .execute().data
    )

    # Aggregate ventas totals
    vt = {
        "n":          len(vs),
        "total":      sum(r["total_factura"] or 0 for r in vs),
        "neto":       sum(r["valor_neto"]    or 0 for r in vs),
        "rf":         sum(r["retefuente"]    or 0 for r in vs),
        "ri":         sum(r["reteiva"]       or 0 for r in vs),
        "rc":         sum(r["reteica"]       or 0 for r in vs),
        "por_cobrar": sum(r["valor_neto"]    or 0 for r in vs if r["estado"] == "PENDIENTE"),
        "vencido":    sum(r["valor_neto"]    or 0 for r in vs if "VENCIDA" in str(r["estado"]).upper()),
    }
    gt = {
        "n":    len(gs),
        "total":sum(r["total_factura"] or 0 for r in gs),
        "neto": sum(r["valor_neto"]    or 0 for r in gs),
        "rf":   sum(r["retefuente"]    or 0 for r in gs),
        "ri":   sum(r["reteiva"]       or 0 for r in gs),
        "rc":   sum(r["reteica"]       or 0 for r in gs),
    }

    NAVY  = colors.HexColor('#1a2744')
    BLUE  = colors.HexColor('#2563eb')
    LGRAY = colors.HexColor('#f1f5f9')
    MGRAY = colors.HexColor('#94a3b8')
    GREEN = colors.HexColor('#059669')
    RED   = colors.HexColor('#dc2626')
    WHITE = colors.white
    DARK  = colors.HexColor('#1e293b')

    def fmt(n): return f"${int(n or 0):,}".replace(',', '.')

    def ps(text, size=9, bold=False, color=DARK, align=0):
        return Paragraph(str(text), ParagraphStyle('_',
            fontSize=size, textColor=color, leading=size*1.35,
            fontName='Helvetica-Bold' if bold else 'Helvetica', alignment=align))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            rightMargin=1.8*cm, leftMargin=1.8*cm,
                            topMargin=1.8*cm, bottomMargin=1.8*cm)
    story = []

    # Header
    hdr = Table([[ps('ESTUDIO CONTABLE ARISTIZÁBAL & ASOCIADOS', 13, True, WHITE),
                  ps('INFORME FINANCIERO', 11, True, WHITE, 2)]],
                colWidths=['*', '*'])
    hdr.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),NAVY),
        ('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12),
        ('LEFTPADDING',(0,0),(-1,-1),14),('RIGHTPADDING',(0,0),(-1,-1),14)]))
    story.append(hdr)

    sub = Table([[ps('T.P. 124567-T · info@contablearistizabal.com.co · Tel: 315-890-4321', 8, color=WHITE),
                  ps(f'Generado: {date.today().strftime("%d/%m/%Y")}', 8, color=WHITE, align=2)]],
                colWidths=['*', '*'])
    sub.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),BLUE),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LEFTPADDING',(0,0),(-1,-1),14),('RIGHTPADDING',(0,0),(-1,-1),14)]))
    story.append(sub)
    story.append(Spacer(1, 0.35*cm))

    # Empresa info
    ei = Table([[ps(e['razon_social'], 12, True), ps(f"NIT: {e['nit']}", 10, align=2)],
                [ps(f"{e['sector']} · {e['ciudad']}", 8, color=MGRAY),
                 ps('Período: Ene – Jun 2026', 8, color=MGRAY, align=2)]],
               colWidths=['*', '*'])
    ei.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LGRAY),
        ('TOPPADDING',(0,0),(-1,0),10),('BOTTOMPADDING',(0,-1),(-1,-1),10),
        ('TOPPADDING',(0,1),(-1,1),3),('BOTTOMPADDING',(0,0),(-1,0),3),
        ('LEFTPADDING',(0,0),(-1,-1),14),('RIGHTPADDING',(0,0),(-1,-1),14),
        ('LINEBELOW',(0,-1),(-1,-1),0.8,BLUE)]))
    story.append(ei)
    story.append(Spacer(1, 0.45*cm))

    # KPIs
    utilidad = vt['neto'] - gt['neto']
    kpi = Table([
        [ps('VENTAS NETAS', 8, color=MGRAY, align=1), ps('POR COBRAR', 8, color=MGRAY, align=1),
         ps('CARTERA VENCIDA', 8, color=MGRAY, align=1), ps('UTILIDAD BRUTA', 8, color=MGRAY, align=1)],
        [ps(fmt(vt['neto']), 12, True, BLUE, 1), ps(fmt(vt['por_cobrar']), 12, True, DARK, 1),
         ps(fmt(vt['vencido']), 12, True, RED, 1), ps(fmt(utilidad), 12, True, GREEN if utilidad > 0 else RED, 1)],
    ], colWidths=['*', '*', '*', '*'])
    kpi.setStyle(TableStyle([
        ('BOX',(0,0),(0,-1),0.8,BLUE),('BOX',(1,0),(1,-1),0.5,colors.HexColor('#cbd5e1')),
        ('BOX',(2,0),(2,-1),0.8,RED),('BOX',(3,0),(3,-1),0.8,GREEN),
        ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4)]))
    story.append(kpi)
    story.append(Spacer(1, 0.55*cm))

    # Ventas table
    story.append(ps('FACTURAS DE VENTA', 10, True, NAVY))
    story.append(Spacer(1, 0.18*cm))
    vh = [ps(h, 8, True, WHITE, 1) for h in ['N°','Fecha','Cliente','Subtotal','IVA','Retefuente','Total','Neto','Estado']]
    vrows = [vh]
    for r in vs:
        ec = RED if 'VENCIDA' in str(r['estado']) else (colors.HexColor('#d97706') if r['estado']=='POR_VENCER' else (GREEN if r['estado']=='PAGADA' else DARK))
        vrows.append([ps(r['numero'],7,align=1), ps(r['fecha'],7,align=1),
            ps((r['cliente_nombre'] or '')[:24],7), ps(fmt(r['subtotal']),7,align=2),
            ps(fmt(r['iva']),7,align=2), ps(fmt(r['retefuente']),7,align=2),
            ps(fmt(r['total_factura']),7,align=2), ps(fmt(r['valor_neto']),7,True,align=2),
            ps(r['estado'][:14],7,color=ec,align=1)])
    vrows.append([ps('TOTAL',8,True,align=1), ps('',7), ps('',7),
        ps(fmt(sum(r['subtotal'] or 0 for r in vs)),8,True,align=2),
        ps(fmt(sum(r['iva'] or 0 for r in vs)),8,True,align=2),
        ps(fmt(vt['rf']),8,True,RED,2), ps(fmt(vt['total']),8,True,align=2),
        ps(fmt(vt['neto']),8,True,BLUE,2), ps('',7)])
    vtbl = Table(vrows, colWidths=[1.6*cm,1.7*cm,3.9*cm,1.9*cm,1.5*cm,1.9*cm,1.9*cm,1.9*cm,1.7*cm])
    vtbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('BACKGROUND',(0,-1),(-1,-1),LGRAY),
        ('ROWBACKGROUNDS',(0,1),(-1,-2),[WHITE,colors.HexColor('#f8fafc')]),
        ('GRID',(0,0),(-1,-1),0.25,colors.HexColor('#e2e8f0')),
        ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
        ('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),
        ('LINEBELOW',(0,-1),(-1,-1),1.2,BLUE)]))
    story.append(vtbl)
    story.append(Spacer(1, 0.55*cm))

    # Gastos table
    story.append(ps('FACTURAS DE GASTOS', 10, True, NAVY))
    story.append(Spacer(1, 0.18*cm))
    gh = [ps(h, 8, True, WHITE, 1) for h in ['N°','Fecha','Proveedor','Categoría','Subtotal','IVA','Retefuente','Total','Neto']]
    grows = [gh]
    for r in gs:
        grows.append([ps(r['numero'],7,align=1), ps(r['fecha'],7,align=1),
            ps((r['proveedor_nombre'] or '')[:20],7), ps((r['categoria'] or '')[:12],7),
            ps(fmt(r['subtotal']),7,align=2), ps(fmt(r['iva']),7,align=2),
            ps(fmt(r['retefuente']),7,align=2), ps(fmt(r['total_factura']),7,align=2),
            ps(fmt(r['valor_neto']),7,True,align=2)])
    grows.append([ps('TOTAL',8,True,align=1), ps('',7), ps('',7), ps('',7),
        ps(fmt(sum(r['subtotal'] or 0 for r in gs)),8,True,align=2),
        ps(fmt(sum(r['iva'] or 0 for r in gs)),8,True,align=2),
        ps(fmt(gt['rf']),8,True,RED,2), ps(fmt(gt['total']),8,True,align=2),
        ps(fmt(gt['neto']),8,True,RED,2)])
    gtbl = Table(grows, colWidths=[1.6*cm,1.7*cm,3.7*cm,2.1*cm,1.9*cm,1.5*cm,1.9*cm,1.8*cm,1.8*cm])
    gtbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('BACKGROUND',(0,-1),(-1,-1),LGRAY),
        ('ROWBACKGROUNDS',(0,1),(-1,-2),[WHITE,colors.HexColor('#f8fafc')]),
        ('GRID',(0,0),(-1,-1),0.25,colors.HexColor('#e2e8f0')),
        ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
        ('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),
        ('LINEBELOW',(0,-1),(-1,-1),1.2,RED)]))
    story.append(gtbl)
    story.append(Spacer(1, 0.55*cm))

    # Retenciones
    story.append(ps('RETENCIONES DEL PERÍODO', 10, True, NAVY))
    story.append(Spacer(1, 0.18*cm))
    rrows = [
        [ps(h, 9, True, WHITE, align) for h, align in [('Concepto',0),('Retefuente',2),('ReteIVA',2),('ReteICA',2),('Total',2)]],
        [ps('Practicadas (retenidas a proveedores)',9),
         ps(fmt(gt['rf']),9,align=2), ps(fmt(gt['ri']),9,align=2), ps(fmt(gt['rc']),9,align=2),
         ps(fmt(gt['rf']+gt['ri']+gt['rc']),9,True,RED,2)],
        [ps('Sufridas (retenidas por clientes)',9),
         ps(fmt(vt['rf']),9,align=2), ps(fmt(vt['ri']),9,align=2), ps(fmt(vt['rc']),9,align=2),
         ps(fmt(vt['rf']+vt['ri']+vt['rc']),9,True,BLUE,2)],
    ]
    saldo = (gt['rf']+gt['ri']+gt['rc']) - (vt['rf']+vt['ri']+vt['rc'])
    rrows.append([ps('Saldo a declarar este período',9,True),
        ps('',9), ps('',9), ps('',9),
        ps(fmt(saldo),10,True,RED if saldo > 0 else GREEN, 2)])
    rtbl = Table(rrows, colWidths=[6.5*cm, 2.4*cm, 2.4*cm, 2.4*cm, 2.3*cm])
    rtbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('BACKGROUND',(0,-1),(-1,-1),LGRAY),
        ('ROWBACKGROUNDS',(0,1),(-1,-2),[WHITE,colors.HexColor('#f8fafc')]),
        ('GRID',(0,0),(-1,-1),0.25,colors.HexColor('#e2e8f0')),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
        ('LINEBELOW',(0,-1),(-1,-1),1.2,BLUE)]))
    story.append(rtbl)
    story.append(Spacer(1, 0.5*cm))

    # Footer
    story.append(HRFlowable(width='100%', thickness=0.4, color=MGRAY))
    story.append(Spacer(1, 0.15*cm))
    story.append(ps('Informe generado automáticamente por ContaBot. Debe ser verificado por el contador '
                    'responsable antes de ser presentado como soporte oficial ante la DIAN u otras entidades.', 7, color=MGRAY))

    doc.build(story)
    buf.seek(0)
    resp = make_response(buf.read())
    resp.headers['Content-Type'] = 'application/pdf'
    nombre_safe = re.sub(r'[^a-zA-Z0-9]', '_', e['razon_social'])[:28]
    resp.headers['Content-Disposition'] = f'attachment; filename="Informe_{nombre_safe}_2026.pdf"'
    return resp


# ── Pre-liquidación de retenciones DIAN ──────────────────────────────────────

@app.route("/api/declaraciones")
@login_required
def declaraciones():
    from calendario import obligaciones_retefte
    emps = (
        sb.table("empresas_clientes")
        .select("id,razon_social,nit,color,regimen")
        .order("id")
        .execute().data
    )
    hoy = date.today()
    MESES_ES = ["enero","febrero","marzo","abril","mayo","junio",
                "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    mes_actual_label = f"{MESES_ES[hoy.month-1].capitalize()} {hoy.year}"

    resultado    = []
    total_global = 0

    for e in emps:
        regimen = e.get("regimen") or "Juridica"
        aplica_rtefte = regimen in ("Juridica", "GranContribuyente")

        g_rows = sb.table("facturas_gastos").select("retefuente,reteiva,reteica").eq("empresa_id", e["id"]).execute().data
        v_rows = sb.table("facturas_venta" ).select("retefuente,reteiva,reteica").eq("empresa_id", e["id"]).execute().data

        rf = round(sum(r["retefuente"] or 0 for r in g_rows)) if aplica_rtefte else 0
        ri = round(sum(r["reteiva"]    or 0 for r in g_rows)) if aplica_rtefte else 0
        rc = round(sum(r["reteica"]    or 0 for r in g_rows)) if aplica_rtefte else 0
        total = rf + ri + rc
        total_global += total

        # Fecha vencimiento real según NIT y calendario DIAN
        if aplica_rtefte:
            obs_rtefte = obligaciones_retefte(e["nit"])
            # Buscar el vencimiento del mes actual o siguiente
            fecha_limite_str = next(
                (o["vencimiento"] for o in obs_rtefte if o["vencimiento"] >= hoy.isoformat()),
                obs_rtefte[-1]["vencimiento"] if obs_rtefte else hoy.isoformat()
            )
            fecha_limite = date.fromisoformat(fecha_limite_str)
            dias = (fecha_limite - hoy).days
            # Formatear fecha en español
            fl_label = f"{fecha_limite.day} de {MESES_ES[fecha_limite.month-1]} {fecha_limite.year}"
        else:
            fecha_limite_str = None
            dias = None
            fl_label = None

        resultado.append({
            "empresa_id":         e["id"],
            "razon_social":       e["razon_social"],
            "nit":                e["nit"],
            "color":              e["color"] or "#6366f1",
            "regimen":            regimen,
            "aplica_rtefte":      aplica_rtefte,
            "retefuente":         rf,
            "reteiva":            ri,
            "reteica":            rc,
            "total":              total,
            "sufrido_retefuente": round(sum(r["retefuente"] or 0 for r in v_rows)),
            "fecha_limite":       fecha_limite_str,
            "fecha_limite_label": fl_label,
            "dias":               dias,
            "estado":             ("VENCIDA" if dias is not None and dias < 0
                                   else "HOY" if dias == 0
                                   else "PENDIENTE" if dias is not None
                                   else "NO_APLICA"),
        })

    return jsonify({
        "mes":               mes_actual_label,
        "empresas":          resultado,
        "total_consolidado": total_global,
    })


# ── Flujo de caja proyectado 60 días ─────────────────────────────────────────

@app.route("/api/empresa/<int:eid>/flujo-caja")
@login_required
def flujo_caja(eid):
    hoy = date.today()

    ventas_rows = (
        sb.table("facturas_venta")
        .select("fecha_vencimiento,valor_neto")
        .eq("empresa_id", eid)
        .in_("estado", ["PENDIENTE", "POR_VENCER"])
        .gte("fecha_vencimiento", hoy.isoformat())
        .execute().data
    )
    gastos_rows = (
        sb.table("facturas_gastos")
        .select("fecha_vencimiento,valor_neto")
        .eq("empresa_id", eid)
        .in_("estado", ["PENDIENTE", "POR_VENCER"])
        .gte("fecha_vencimiento", hoy.isoformat())
        .execute().data
    )
    cartera_rows = (
        sb.table("facturas_venta")
        .select("valor_neto")
        .eq("empresa_id", eid)
        .like("estado", "VENCIDA%")
        .execute().data
    )
    cartera_total = sum(r["valor_neto"] or 0 for r in cartera_rows)

    semanas = []
    for i in range(8):
        ini = hoy + timedelta(days=i * 7)
        fin = ini + timedelta(days=6)
        ing = sum(r["valor_neto"] or 0 for r in ventas_rows
                  if ini <= date.fromisoformat(r["fecha_vencimiento"]) <= fin)
        egr = sum(r["valor_neto"] or 0 for r in gastos_rows
                  if ini <= date.fromisoformat(r["fecha_vencimiento"]) <= fin)
        semanas.append({
            "label":    f"{ini.strftime('%d/%m')}–{fin.strftime('%d/%m')}",
            "ingresos": round(ing),
            "egresos":  round(egr),
            "neto":     round(ing - egr),
        })

    return jsonify({"semanas": semanas, "cartera_vencida": round(cartera_total)})


@app.route("/api/empresa/<int:eid>/declaraciones")
@login_required
def declaraciones_empresa(eid):
    from datetime import date as d
    e_rows = sb.table("empresas_clientes").select("*").eq("id", eid).execute().data
    if not e_rows:
        return jsonify({"error": "Empresa no encontrada"}), 404
    e = e_rows[0]

    ventas = sb.table("facturas_venta").select("fecha,subtotal,iva,retefuente,reteiva,reteica,total_factura,valor_neto").eq("empresa_id", eid).execute().data
    gastos = sb.table("facturas_gastos").select("fecha,subtotal,iva,retefuente,reteiva,reteica,total_factura,valor_neto").eq("empresa_id", eid).execute().data

    def mes(r):
        try: return int((r.get("fecha") or "")[:7].split("-")[1])
        except: return 0

    def cuatrimestre(r):
        m = mes(r)
        if 1 <= m <= 4: return 1
        if 5 <= m <= 8: return 2
        return 3

    def bimestre(r):
        m = mes(r)
        return (m + 1) // 2 if m > 0 else 0

    # IVA F-300 por cuatrimestre
    f300 = []
    labels_c = {1: "Ene–Abr", 2: "May–Ago", 3: "Sep–Dic"}
    for c in [1, 2, 3]:
        vv = [r for r in ventas if cuatrimestre(r) == c]
        gg = [r for r in gastos if cuatrimestre(r) == c]
        iva_gen  = round(sum(r["iva"] or 0 for r in vv))
        iva_desc = round(sum(r["iva"] or 0 for r in gg))
        iva_pagar = max(0, iva_gen - iva_desc)
        f300.append({
            "cuatrimestre": c,
            "periodo":      labels_c[c],
            "base_ventas":  round(sum(r["subtotal"] or 0 for r in vv)),
            "iva_generado": iva_gen,
            "iva_descontable": iva_desc,
            "iva_a_pagar":  iva_pagar,
            "n_facturas_v": len(vv),
            "n_facturas_g": len(gg),
        })

    # Retefuente F-350 por mes
    MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
    f350 = []
    for m_num in range(1, 13):
        gg = [r for r in gastos if mes(r) == m_num]
        rfte = round(sum(r["retefuente"] or 0 for r in gg))
        if rfte > 0 or gg:
            f350.append({
                "mes":       m_num,
                "periodo":   MESES[m_num - 1],
                "base":      round(sum(r["subtotal"] or 0 for r in gg)),
                "retefte":   rfte,
                "n_facturas": len(gg),
            })

    # ICA por bimestre
    TASA_ICA = 4.14 / 1000  # 4.14‰ Bogotá (ajustable por ciudad)
    labels_b = {1:"Ene–Feb",2:"Mar–Abr",3:"May–Jun",4:"Jul–Ago",5:"Sep–Oct",6:"Nov–Dic"}
    ica = []
    for b in range(1, 7):
        vv = [r for r in ventas if bimestre(r) == b]
        base = round(sum(r["subtotal"] or 0 for r in vv))
        ica.append({
            "bimestre":   b,
            "periodo":    labels_b[b],
            "base":       base,
            "tasa":       "4.14‰",
            "ica_a_pagar": round(base * TASA_ICA),
            "n_facturas": len(vv),
        })

    regimen = e.get("regimen") or "Juridica"
    aplica_iva    = regimen in ("Juridica", "GranContribuyente")
    aplica_rtefte = regimen in ("Juridica", "GranContribuyente")
    aplica_ica    = regimen in ("Juridica", "GranContribuyente", "Simple")

    return jsonify({
        "ok":      True,
        "regimen": regimen,
        "empresa": {"id": e["id"], "razon_social": e["razon_social"], "nit": e["nit"]},
        "f300":  f300 if aplica_iva else [],
        "f350":  f350 if aplica_rtefte else [],
        "ica":   ica  if aplica_ica else [],
        "aplica_iva":    aplica_iva,
        "aplica_rtefte": aplica_rtefte,
        "aplica_ica":    aplica_ica,
    })


# ── Export Excel — Formato Eduardo (CONTABILIDAD 2026) ────────────────────────

def _mes_num(fecha):
    try: return int(str(fecha or "")[:7].split("-")[1])
    except: return 0

def _bimestre(m): return (m + 1) // 2 if m else 0

def _cuatrimestre(m):
    if 1 <= m <= 4: return 1
    if 5 <= m <= 8: return 2
    return 3 if m else 0

def _cod_iva(subtotal, iva):
    if not subtotal or subtotal == 0: return "EX0 EXENTO"
    tasa = (iva or 0) / subtotal
    if abs(tasa - 0.19) < 0.02: return "IVA 19 GEN"
    if abs(tasa - 0.05) < 0.02: return "IVA 5 GEN"
    return "EX0 EXENTO"

def _pct_iva(subtotal, iva):
    if not subtotal or subtotal == 0: return 0
    return round((iva or 0) / subtotal, 4)


@app.route("/api/empresa/<int:eid>/informe-excel")
@login_required
def informe_excel(eid):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return jsonify({"error": "pip install openpyxl"}), 500
    import io
    from flask import make_response
    from datetime import date as d

    e_rows = sb.table("empresas_clientes").select("*").eq("id", eid).execute().data
    if not e_rows:
        return jsonify({"error": "Empresa no encontrada"}), 404
    e = e_rows[0]

    vs = sb.table("facturas_venta").select(
        "numero,cufe,fecha,cliente_nombre,cliente_nit,subtotal,iva,"
        "retefuente,reteiva,reteica,total_factura,valor_neto,estado,concepto"
    ).eq("empresa_id", eid).order("fecha").execute().data

    gs = sb.table("facturas_gastos").select(
        "numero,cufe,fecha,proveedor_nombre,proveedor_nit,categoria,"
        "subtotal,iva,retefuente,reteiva,reteica,total_factura,valor_neto,estado"
    ).eq("empresa_id", eid).order("fecha").execute().data

    # ── helpers de estilo ──────────────────────────────────────────────────────
    HDR_FILL = PatternFill("solid", fgColor="1E3A5F")
    HDR_FONT = Font(color="FFFFFF", bold=True, size=10)
    HDR_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(style="thin", color="CCCCCC")
    BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
    NUM_FMT = '#,##0'

    def style_header(ws, cols, row=1):
        for ci, col in enumerate(cols, 1):
            cell = ws.cell(row=row, column=ci, value=col)
            cell.font = HDR_FONT; cell.fill = HDR_FILL
            cell.alignment = HDR_ALIGN; cell.border = BORDER

    def style_row(ws, row_num, n_cols, is_num_cols=None):
        fill = PatternFill("solid", fgColor="F8FAFC") if row_num % 2 == 0 else None
        for ci in range(1, n_cols + 1):
            cell = ws.cell(row=row_num, column=ci)
            cell.border = BORDER
            if fill: cell.fill = fill
            if is_num_cols and ci in is_num_cols:
                cell.number_format = NUM_FMT
                cell.alignment = Alignment(horizontal="right")

    wb = openpyxl.Workbook()

    # ── Hoja VENTAS ────────────────────────────────────────────────────────────
    ws_v = wb.active; ws_v.title = "VENTAS"
    ws_v.row_dimensions[1].height = 40

    title = f"REGISTRO DE VENTAS — {e['razon_social']} | NIT {e['nit']} | 2026"
    ws_v.merge_cells("A1:W1")
    tc = ws_v["A1"]; tc.value = title
    tc.font = Font(bold=True, size=12, color="1E3A5F")
    tc.alignment = Alignment(horizontal="center", vertical="center")

    V_COLS = ["Nº","Fecha","Mes","Bimestre","Cuatrimestre","Nº Factura","CUFE",
              "Cliente","NIT","Concepto","Contrato/Orden","Cuenta PUC",
              "Base Gravable","Cód. IVA","% IVA","IVA Generado",
              "RteFte 135515","ReteIVA 135517","ReteICA 135518",
              "Total Factura","Neto a Recibir","Estado Cobro","Observaciones"]
    style_header(ws_v, V_COLS, row=2)

    NUM_COLS_V = {13,16,17,18,19,20,21}
    for i, r in enumerate(vs, 1):
        m = _mes_num(r["fecha"])
        row_data = [
            i, r["fecha"], m, _bimestre(m), _cuatrimestre(m),
            r["numero"], r.get("cufe",""),
            r["cliente_nombre"], r.get("cliente_nit",""),
            r.get("concepto",""), "", "",
            r["subtotal"] or 0,
            _cod_iva(r["subtotal"], r["iva"]),
            _pct_iva(r["subtotal"], r["iva"]),
            r["iva"] or 0,
            r["retefuente"] or 0, r["reteiva"] or 0, r["reteica"] or 0,
            r["total_factura"] or 0, r["valor_neto"] or 0,
            r["estado"], ""
        ]
        for ci, val in enumerate(row_data, 1):
            ws_v.cell(row=i+2, column=ci, value=val)
        style_row(ws_v, i+2, len(V_COLS), NUM_COLS_V)

    # Anchos columna VENTAS
    for ci, w in enumerate([5,12,5,8,10,14,20,28,14,20,16,12,
                             14,12,8,14,14,14,14,14,14,12,16], 1):
        ws_v.column_dimensions[get_column_letter(ci)].width = w

    # ── Hoja COMPRAS ───────────────────────────────────────────────────────────
    ws_g = wb.create_sheet("COMPRAS")
    ws_g.row_dimensions[1].height = 40
    ws_g.merge_cells("A1:Z1")
    tc2 = ws_g["A1"]; tc2.value = f"REGISTRO DE COMPRAS — {e['razon_social']} | NIT {e['nit']} | 2026"
    tc2.font = Font(bold=True, size=12, color="1E3A5F")
    tc2.alignment = Alignment(horizontal="center", vertical="center")

    G_COLS = ["Nº","Fecha","Mes","Bimestre","Cuatrimestre","Nº Factura",
              "Proveedor","NIT","Concepto / Detalle","Tipo (Bien/Servicio)","CC","Cuenta PUC",
              "Base Gravable","Cód. IVA","% IVA","VALOR IVA",
              "Cód. RteFte","% RteFte","Valor RteFte","% ReteICA","Valor ReteICA",
              "Total Factura","Neto a Pagar","Forma Pago","Estado","Observaciones"]
    style_header(ws_g, G_COLS, row=2)

    NUM_COLS_G = {13,16,19,21,22,23}
    TIPO_MAP = {"honorarios":"Servicio","servicios":"Servicio","transporte":"Servicio",
                "insumos":"Bien","tecnologia":"Bien"}
    for i, r in enumerate(gs, 1):
        m = _mes_num(r["fecha"])
        cat = (r.get("categoria") or "").lower()
        tipo = TIPO_MAP.get(cat, "Servicio")
        pct_rf = round((r["retefuente"] or 0) / (r["subtotal"] or 1), 4) if r.get("subtotal") else 0
        row_data = [
            i, r["fecha"], m, _bimestre(m), _cuatrimestre(m),
            r["numero"], r["proveedor_nombre"], r.get("proveedor_nit",""),
            r.get("categoria",""), tipo, "", "",
            r["subtotal"] or 0,
            _cod_iva(r["subtotal"], r["iva"]),
            _pct_iva(r["subtotal"], r["iva"]),
            r["iva"] or 0,
            "", pct_rf, r["retefuente"] or 0,
            0, r["reteica"] or 0,
            r["total_factura"] or 0, r["valor_neto"] or 0,
            "", r["estado"], ""
        ]
        for ci, val in enumerate(row_data, 1):
            ws_g.cell(row=i+2, column=ci, value=val)
        style_row(ws_g, i+2, len(G_COLS), NUM_COLS_G)

    for ci, w in enumerate([5,12,5,8,10,14,28,14,22,12,8,12,
                             14,12,8,14,14,8,14,8,12,14,14,12,12,16], 1):
        ws_g.column_dimensions[get_column_letter(ci)].width = w

    # ── Hoja IVA F-300 ─────────────────────────────────────────────────────────
    ws_iva = wb.create_sheet("IVA F-300")
    ws_iva.merge_cells("A1:F1")
    h = ws_iva["A1"]; h.value = f"DECLARACIÓN IVA F-300 — {e['razon_social']} | 2026"
    h.font = Font(bold=True, size=12, color="1E3A5F")
    h.alignment = Alignment(horizontal="center")
    style_header(ws_iva, ["Concepto","Cuatrimestre 1\n(Ene-Abr)",
                           "Cuatrimestre 2\n(May-Ago)","Cuatrimestre 3\n(Sep-Dic)",
                           "TOTAL AÑO","Casilla F-300"], row=2)

    def cuatri_data(rows, q):
        return [r for r in rows if _cuatrimestre(_mes_num(r["fecha"])) == q]

    conceptos_iva = [
        ("Base gravable ventas",         lambda q: sum(r["subtotal"] or 0 for r in cuatri_data(vs,q))),
        ("IVA generado (ventas)",         lambda q: sum(r["iva"] or 0 for r in cuatri_data(vs,q))),
        ("Base gravable compras",         lambda q: sum(r["subtotal"] or 0 for r in cuatri_data(gs,q))),
        ("IVA descontable (compras)",     lambda q: sum(r["iva"] or 0 for r in cuatri_data(gs,q))),
        ("IVA a pagar (Generado-Desct.)", lambda q: max(0, sum(r["iva"] or 0 for r in cuatri_data(vs,q)) - sum(r["iva"] or 0 for r in cuatri_data(gs,q)))),
    ]
    CASILLAS = ["","","","","67"]
    for ri, (concepto, fn) in enumerate(conceptos_iva, 3):
        vals = [fn(1), fn(2), fn(3)]
        row_data = [concepto, *vals, sum(vals), CASILLAS[ri-3]]
        for ci, val in enumerate(row_data, 1):
            cell = ws_iva.cell(row=ri, column=ci, value=val)
            cell.border = BORDER
            if ci > 1 and ci < 6 and isinstance(val, (int,float)):
                cell.number_format = NUM_FMT
        if concepto.startswith("IVA a pagar"):
            for ci in range(2, 6):
                ws_iva.cell(row=ri, column=ci).font = Font(bold=True, color="C0392B")

    # ── Hoja RFTE 350 ──────────────────────────────────────────────────────────
    ws_rf = wb.create_sheet("RFTE 350")
    ws_rf.merge_cells("A1:O1")
    h2 = ws_rf["A1"]; h2.value = f"RETENCIÓN EN LA FUENTE F-350 — {e['razon_social']} | 2026"
    h2.font = Font(bold=True, size=12, color="1E3A5F")
    h2.alignment = Alignment(horizontal="center")
    MESES_NOM = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
    style_header(ws_rf, ["Concepto","Código",*MESES_NOM,"Total Año"], row=2)

    def mes_data(rows, m): return [r for r in rows if _mes_num(r["fecha"]) == m]
    rf_vals = [round(sum(r["retefuente"] or 0 for r in mes_data(gs, m))) for m in range(1,13)]
    rf_row = ["Retención en la fuente practicada", "75-96", *rf_vals, sum(rf_vals)]
    for ci, val in enumerate(rf_row, 1):
        cell = ws_rf.cell(row=3, column=ci, value=val)
        cell.border = BORDER
        if ci > 2 and isinstance(val, (int,float)):
            cell.number_format = NUM_FMT
            if val > 0: cell.font = Font(bold=True, color="C0392B")

    # ── Hoja ICA ───────────────────────────────────────────────────────────────
    ws_ica = wb.create_sheet("ICA")
    ws_ica.merge_cells("A1:I1")
    h3 = ws_ica["A1"]; h3.value = f"DECLARACIÓN ICA — {e['razon_social']} | 2026"
    h3.font = Font(bold=True, size=12, color="1E3A5F")
    h3.alignment = Alignment(horizontal="center")
    BIM_LABELS = ["Bim 1\n(Ene-Feb)","Bim 2\n(Mar-Abr)","Bim 3\n(May-Jun)",
                  "Bim 4\n(Jul-Ago)","Bim 5\n(Sep-Oct)","Bim 6\n(Nov-Dic)"]
    style_header(ws_ica, ["Concepto",*BIM_LABELS,"TOTAL AÑO"], row=2)

    def bim_data(rows, b): return [r for r in rows if _bimestre(_mes_num(r["fecha"])) == b]
    TASA_ICA = 4.14 / 1000
    ica_bases = [round(sum(r["subtotal"] or 0 for r in bim_data(vs, b))) for b in range(1,7)]
    ica_vals  = [round(b * TASA_ICA) for b in ica_bases]

    for ri, (label, vals) in enumerate([("Base gravable (ventas)", ica_bases),
                                         ("ICA a pagar (4.14‰)", ica_vals)], 3):
        row_data = [label, *vals, sum(vals)]
        for ci, val in enumerate(row_data, 1):
            cell = ws_ica.cell(row=ri, column=ci, value=val)
            cell.border = BORDER
            if ci > 1 and isinstance(val,(int,float)):
                cell.number_format = NUM_FMT
        if label.startswith("ICA a pagar"):
            for ci in range(2, 9):
                ws_ica.cell(row=ri, column=ci).font = Font(bold=True, color="C0392B")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    resp = make_response(buf.read())
    resp.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    nombre = re.sub(r'[^a-zA-Z0-9]', '_', e['razon_social'])[:28]
    resp.headers['Content-Disposition'] = f'attachment; filename="ContaBot_{nombre}_2026.xlsx"'
    return resp


# ── Importar Excel DIAN — conciliación ────────────────────────────────────────

@app.route("/api/empresa/<int:eid>/importar-dian", methods=["POST"])
@login_required
def importar_dian(eid):
    import io, re as _re
    try:
        import openpyxl
    except ImportError:
        return jsonify({"ok": False, "error": "pip install openpyxl"}), 500

    archivo = request.files.get("archivo")
    if not archivo:
        return jsonify({"ok": False, "error": "No se recibió archivo"}), 400

    try:
        wb = openpyxl.load_workbook(io.BytesIO(archivo.read()), read_only=True, data_only=True)
    except Exception as ex:
        return jsonify({"ok": False, "error": f"No se pudo leer el Excel: {ex}"}), 400

    CUFE_RE = _re.compile(r"^[a-f0-9]{96}$", _re.IGNORECASE)

    # Buscar CUFEs en todas las hojas
    cufes_dian = {}   # cufe → {numero, fecha, nit_emisor, nombre_emisor, total}
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        headers = None
        cufe_col = num_col = fecha_col = nit_col = nombre_col = total_col = None

        for ri, row in enumerate(ws.iter_rows(values_only=True)):
            if headers is None:
                # Detectar fila de encabezados
                row_str = [str(c or "").lower() for c in row]
                if any("cufe" in c for c in row_str):
                    headers = row_str
                    for ci, h in enumerate(headers):
                        if "cufe" in h: cufe_col = ci
                        elif any(x in h for x in ["factura","numero","número","n°"]): num_col = ci
                        elif "fecha" in h: fecha_col = ci
                        elif "nit" in h: nit_col = ci
                        elif any(x in h for x in ["razon","razón","nombre","emisor"]): nombre_col = ci
                        elif any(x in h for x in ["total","valor"]): total_col = ci
                    continue
                # Sin encabezados: buscar CUFEs directamente en celdas
                for ci, cell in enumerate(row):
                    val = str(cell or "").strip()
                    if CUFE_RE.match(val):
                        cufes_dian[val.lower()] = {"cufe": val.lower(), "numero": "", "fecha": "", "nit_emisor": "", "nombre_emisor": "", "total": 0}
                continue

            # Con encabezados detectados
            if cufe_col is not None and len(row) > cufe_col:
                val = str(row[cufe_col] or "").strip()
                if CUFE_RE.match(val):
                    cufes_dian[val.lower()] = {
                        "cufe":         val.lower(),
                        "numero":       str(row[num_col] or "") if num_col is not None else "",
                        "fecha":        str(row[fecha_col] or "")[:10] if fecha_col is not None else "",
                        "nit_emisor":   str(row[nit_col] or "") if nit_col is not None else "",
                        "nombre_emisor":str(row[nombre_col] or "") if nombre_col is not None else "",
                        "total":        float(row[total_col] or 0) if total_col is not None else 0,
                    }

    if not cufes_dian:
        return jsonify({"ok": False, "error": "No se encontraron CUFEs en el archivo. ¿Es el Excel exportado del portal DIAN?"}), 400

    # Comparar contra lo que ya está en ContaBot
    registradas = sb.table("facturas_gastos").select("cufe,numero").eq("empresa_id", eid).execute().data
    cufes_contabot = {(r.get("cufe") or "").lower() for r in registradas}

    ya_registradas = []
    nuevas         = []
    for cufe, info in cufes_dian.items():
        if cufe in cufes_contabot:
            ya_registradas.append(info)
        else:
            nuevas.append(info)

    return jsonify({
        "ok":            True,
        "total_dian":    len(cufes_dian),
        "ya_en_contabot": len(ya_registradas),
        "nuevas":        len(nuevas),
        "detalle_nuevas": nuevas[:50],
    })


# ── Marcar factura como pagada ─────────────────────────────────────────────────

@app.route("/api/factura/<tipo>/<path:numero>/empresa/<int:eid>/pagar", methods=["POST"])
@login_required
def marcar_pagada(tipo, numero, eid):
    if tipo not in ("venta", "gasto"):
        return jsonify({"ok": False, "error": "Tipo inválido"}), 400
    tabla = "facturas_venta" if tipo == "venta" else "facturas_gastos"
    try:
        sb.table(tabla).update({"estado": "PAGADA"}).eq("numero", numero).eq("empresa_id", eid).execute()
        return jsonify({"ok": True})
    except Exception as ex:
        return jsonify({"ok": False, "error": str(ex)}), 400


# ── Conciliación bancaria — cruce de extracto CSV vs facturas ─────────────────

@app.route("/api/empresa/<int:eid>/conciliacion", methods=["POST"])
@login_required
def conciliacion_bancaria(eid):
    try:
        import pandas as pd
    except ImportError:
        return jsonify({"ok": False, "error": "pandas no disponible"}), 500
    import io

    if "archivo" not in request.files:
        return jsonify({"ok": False, "error": "No se recibió archivo"}), 400

    texto = request.files["archivo"].read().decode("utf-8", errors="replace")

    try:
        df = pd.read_csv(io.StringIO(texto))
    except Exception as ex:
        return jsonify({"ok": False, "error": f"No se pudo leer el CSV: {str(ex)}"}), 400

    df.columns = [c.strip().lower() for c in df.columns]

    monto_col = next((c for c in df.columns if any(k in c for k in ['monto','valor','importe','credito','credit','debit','debito'])), None)
    fecha_col = next((c for c in df.columns if any(k in c for k in ['fecha','date','dia'])), None)
    desc_col  = next((c for c in df.columns if any(k in c for k in ['descripcion','desc','concepto','referencia','detail'])), None)

    if not monto_col:
        cols = list(df.columns)
        return jsonify({"ok": False, "error": f"No se encontró columna de monto. Columnas detectadas: {cols}"}), 400

    df['_monto'] = (
        df[monto_col].astype(str)
        .str.replace(r'[$\s]', '', regex=True)
        .str.replace(r'[.,](?=\d{3})', '', regex=True)
        .str.replace(',', '.', regex=False)
    )
    df['_monto'] = pd.to_numeric(df['_monto'], errors='coerce').fillna(0).abs()

    ventas_rows = (
        sb.table("facturas_venta")
        .select("numero,valor_neto,cliente_nombre,fecha_vencimiento,estado")
        .eq("empresa_id", eid)
        .not_.eq("estado", "PAGADA")
        .execute().data
    )
    gastos_rows = (
        sb.table("facturas_gastos")
        .select("numero,valor_neto,proveedor_nombre,fecha_vencimiento,estado")
        .eq("empresa_id", eid)
        .not_.eq("estado", "PAGADA")
        .execute().data
    )
    # Normalise gastos to share campo 'cliente_nombre'
    for r in gastos_rows:
        r["cliente_nombre"] = r.pop("proveedor_nombre", "")

    todas = ventas_rows + gastos_rows
    coincidencias, sin_match = [], []

    for _, row in df.iterrows():
        monto = row['_monto']
        if monto < 1000:
            continue
        fecha = str(row[fecha_col]) if fecha_col else ''
        desc  = str(row[desc_col])  if desc_col  else ''
        match = None
        for f in todas:
            neto = f['valor_neto'] or 0
            if abs(monto - neto) <= max(neto * 0.015, 5000):
                match = f
                break
        if match:
            coincidencias.append({
                "extracto_monto":  int(monto),
                "extracto_fecha":  fecha,
                "extracto_desc":   desc[:60],
                "factura_numero":  match['numero'],
                "factura_tercero": match['cliente_nombre'],
                "factura_neto":    int(match['valor_neto'] or 0),
                "diferencia":      int(abs(monto - (match['valor_neto'] or 0))),
                "tipo":            "exacto" if abs(monto - (match['valor_neto'] or 0)) < 1000 else "aproximado",
            })
        else:
            sin_match.append({"monto": int(monto), "fecha": fecha, "descripcion": desc[:60]})

    return jsonify({
        "ok": True,
        "resumen": {
            "total_filas": len(df),
            "matches":     len(coincidencias),
            "sin_match":   len(sin_match),
            "pct_match":   round(len(coincidencias) / max(len(df), 1) * 100, 1),
        },
        "coincidencias": coincidencias,
        "sin_match":     sin_match[:30],
    })


# ── Calendario tributario ─────────────────────────────────────────────────────

@app.route("/api/calendario")
@login_required
def get_calendario():
    from datetime import date as d
    empresas = sb.table("empresas_clientes").select("id,nit,razon_social,ciudad,regimen").execute().data
    resultado = []
    hoy = d.today()
    for e in empresas:
        regimen = e.get("regimen") or "Juridica"
        obs = todas_las_obligaciones(e.get("nit", ""), regimen=regimen)
        for ob in obs:
            vto = d.fromisoformat(ob["vencimiento"])
            dias = (vto - hoy).days
            if dias < -30:
                estado = "vencida"
            elif dias < 0:
                estado = "vencida"
            elif dias <= 7:
                estado = "urgente"
            elif dias <= 30:
                estado = "proxima"
            else:
                estado = "ok"
            resultado.append({
                "empresa_id":    e["id"],
                "empresa":       e["razon_social"],
                "ciudad":        e.get("ciudad", ""),
                "nit":           e.get("nit", ""),
                "tipo":          ob["tipo"],
                "periodo":       ob["periodo"],
                "vencimiento":   ob["vencimiento"],
                "frecuencia":    ob["frecuencia"],
                "dias_restantes": dias,
                "estado":        estado,
            })
    resultado.sort(key=lambda x: x["vencimiento"])
    return jsonify({"ok": True, "obligaciones": resultado})


@app.route("/api/calendario/notificar", methods=["POST"])
@login_required
def notificar_obligaciones():
    """Envía Telegram con obligaciones que vencen en los próximos 7 días."""
    empresas = sb.table("empresas_clientes").select("id,nit,razon_social").execute().data
    proximas = obligaciones_proximas(empresas, dias=7)
    if not proximas:
        return jsonify({"ok": True, "enviadas": 0})

    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return jsonify({"ok": False, "error": "Telegram no configurado"})

    import urllib.request, urllib.parse, json as _json
    lineas = ["*Obligaciones tributarias próximas (7 días)*\n"]
    for p in proximas:
        ob   = p["obligacion"]
        dias = p["dias_restantes"]
        emoji = "🔴" if dias <= 2 else "🟡"
        lineas.append(
            f"{emoji} *{ob['tipo']}* — {p['empresa']}\n"
            f"   Período: {ob['periodo']} | Vence: {ob['vencimiento']} ({dias}d)"
        )
    texto = "\n".join(lineas)
    payload = _json.dumps({"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as ex:
        return jsonify({"ok": False, "error": str(ex)})
    return jsonify({"ok": True, "enviadas": len(proximas)})


# ── Subir factura electrónica DIAN (PDF / XML / ZIP) ─────────────────────────

@app.route("/api/subir-factura", methods=["POST"])
@login_required
def subir_factura():
    from datetime import datetime as dt
    archivo = request.files.get("archivo")
    if not archivo:
        return jsonify({"ok": False, "error": "No se recibió archivo"}), 400

    fname = archivo.filename or ""
    ext   = fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
    if ext not in ("pdf", "xml", "zip"):
        return jsonify({"ok": False, "error": "Solo se aceptan PDF, XML o ZIP"}), 400

    data = archivo.read()
    tmp_dir = FACTURAS_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Descomprimir ZIP si aplica
    if ext == "zip":
        archivos = descomprimir_zip(data, tmp_dir)
        if not archivos:
            return jsonify({"ok": False, "error": "ZIP sin PDF/XML válido"}), 400
    else:
        file_path = tmp_dir / fname
        file_path.write_bytes(data)
        archivos = [file_path]

    # Extraer datos
    datos = None
    file_usado = None
    for fp in archivos:
        datos = extraer_xml(str(fp)) if fp.suffix.lower() == ".xml" else extraer_pdf(str(fp))
        if datos:
            file_usado = fp
            break

    if not datos:
        return jsonify({"ok": False, "error": "No se pudieron extraer datos de la factura"}), 400

    # Detectar o crear empresa por NIT receptor
    empresa = detectar_o_crear_empresa(datos, sb)

    empresa_id = empresa["id"] if empresa else None
    empresa_nombre = empresa["razon_social"] if empresa else "Empresa desconocida"

    # Verificar si es empresa conocida — si no, avisar por Telegram con botones y devolver info al UI
    if not empresa_id:
        pendiente_id = guardar_empresa_pendiente(datos, fuente="upload", sb=sb)
        notificar_empresa_desconocida(datos, fuente="upload", pendiente_id=pendiente_id)
        empresas_all = sb.table("empresas_clientes").select("id,nit,razon_social").execute().data
        return jsonify({
            "ok": True,
            "datos": datos,
            "empresa_detectada": False,
            "pendiente_id": pendiente_id,
            "empresas_disponibles": empresas_all,
            "mensaje": f"No se detectó la empresa receptora (NIT: {datos.get('receptor_nit') or 'no encontrado'}). Te pregunté en Telegram — o selecciona manualmente.",
        })

    # Mover archivo a carpeta definitiva
    empresa_dir = FACTURAS_DIR / str(empresa_id)
    empresa_dir.mkdir(parents=True, exist_ok=True)
    destino = empresa_dir / (file_usado.name)
    file_usado.rename(destino)

    # Verificar duplicado
    numero = datos.get("numero", "")
    ya = sb.table("facturas_gastos").select("id").eq("empresa_id", empresa_id).eq("numero", numero).execute()
    if ya.data:
        return jsonify({
            "ok": True,
            "datos": datos,
            "empresa": empresa_nombre,
            "duplicada": True,
            "mensaje": f"La factura {numero} ya estaba registrada.",
        })

    # Guardar en Supabase
    sb.table("facturas_gastos").insert({
        "empresa_id":       empresa_id,
        "numero":           numero,
        "cufe":             datos.get("cufe", ""),
        "fecha":            datos.get("fecha") or dt.today().strftime("%Y-%m-%d"),
        "proveedor_nit":    datos.get("proveedor_nit", ""),
        "proveedor_nombre": datos.get("proveedor_nombre", ""),
        "proveedor_ciudad": datos.get("proveedor_ciudad", ""),
        "subtotal":         datos.get("subtotal", 0),
        "iva":              datos.get("iva", 0),
        "total_factura":    datos.get("total_factura", 0),
        "valor_neto":       datos.get("valor_neto", datos.get("total_factura", 0)),
        "estado":           "pendiente",
        "archivo_pdf":      str(destino),
        "fuente":           "upload",
    }).execute()

    notificar_factura(datos, empresa_nombre, tipo="compra", fuente="upload")

    return jsonify({
        "ok": True,
        "datos": datos,
        "empresa": empresa_nombre,
        "empresa_id": empresa_id,
        "duplicada": False,
        "mensaje": f"Factura {numero} registrada correctamente en {empresa_nombre}.",
    })


# ── Guardar factura con empresa seleccionada manualmente ─────────────────────

@app.route("/api/subir-factura/confirmar", methods=["POST"])
@login_required
def confirmar_factura():
    from datetime import datetime as dt
    body       = request.get_json()
    datos      = body.get("datos", {})
    empresa_id = body.get("empresa_id")
    if not empresa_id:
        return jsonify({"ok": False, "error": "empresa_id requerido"}), 400

    empresa_rows = sb.table("empresas_clientes").select("razon_social").eq("id", empresa_id).execute().data
    empresa_nombre = empresa_rows[0]["razon_social"] if empresa_rows else f"Empresa {empresa_id}"

    numero = datos.get("numero", "")
    ya = sb.table("facturas_gastos").select("id").eq("empresa_id", empresa_id).eq("numero", numero).execute()
    if ya.data:
        return jsonify({"ok": True, "duplicada": True, "mensaje": f"La factura {numero} ya estaba registrada."})

    sb.table("facturas_gastos").insert({
        "empresa_id":       empresa_id,
        "numero":           numero,
        "cufe":             datos.get("cufe", ""),
        "fecha":            datos.get("fecha") or dt.today().strftime("%Y-%m-%d"),
        "proveedor_nit":    datos.get("proveedor_nit", ""),
        "proveedor_nombre": datos.get("proveedor_nombre", ""),
        "proveedor_ciudad": datos.get("proveedor_ciudad", ""),
        "subtotal":         datos.get("subtotal", 0),
        "iva":              datos.get("iva", 0),
        "total_factura":    datos.get("total_factura", 0),
        "valor_neto":       datos.get("valor_neto", datos.get("total_factura", 0)),
        "estado":           "pendiente",
        "fuente":           "upload",
    }).execute()

    notificar_factura(datos, empresa_nombre, tipo="compra", fuente="upload")

    return jsonify({"ok": True, "duplicada": False, "empresa": empresa_nombre,
                    "mensaje": f"Factura {numero} registrada en {empresa_nombre}."})


# ── Telegram Webhook ─────────────────────────────────────────────────────────

@app.route("/api/telegram/webhook", methods=["POST"])
def telegram_webhook():
    """Recibe callbacks de Telegram (botones inline) y procesa confirmaciones de empresa."""
    update = request.get_json(silent=True) or {}

    if "callback_query" not in update:
        return jsonify({"ok": True})

    cq         = update["callback_query"]
    cq_id      = cq["id"]
    data       = cq.get("data", "")
    chat_id    = str(cq["message"]["chat"]["id"])
    message_id = cq["message"]["message_id"]

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    def answer(text=""):
        """Cierra el spinner del botón."""
        try:
            import urllib.request as _ur
            payload = json.dumps({"callback_query_id": cq_id, "text": text}).encode()
            _ur.urlopen(_ur.Request(
                f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                data=payload, headers={"Content-Type": "application/json"}
            ), timeout=5)
        except Exception:
            pass

    def edit_message(text):
        """Edita el mensaje original para mostrar el resultado."""
        try:
            import urllib.request as _ur
            payload = json.dumps({
                "chat_id": chat_id, "message_id": message_id,
                "text": text, "parse_mode": "Markdown",
            }).encode()
            _ur.urlopen(_ur.Request(
                f"https://api.telegram.org/bot{token}/editMessageText",
                data=payload, headers={"Content-Type": "application/json"}
            ), timeout=5)
        except Exception:
            pass

    if data.startswith("confirmar_empresa:"):
        pendiente_id = data.split(":", 1)[1]
        answer("Procesando…")
        try:
            row = sb.table("empresas_pendientes").select("*").eq("id", pendiente_id).execute().data
            if not row:
                edit_message("⚠️ No se encontraron los datos pendientes. Puede que ya hayan sido procesados.")
                return jsonify({"ok": True})

            p = row[0]
            nit    = p["nit"]
            nombre = p["razon_social"] or f"Empresa NIT {nit}"
            ciudad = p["ciudad"] or ""
            datos  = p["factura_data"] or {}
            fuente = p["fuente"] or "upload"

            # Crear empresa
            import random
            COLORES = ["#6366f1","#10b981","#f59e0b","#ef4444","#3b82f6","#8b5cf6","#ec4899","#14b8a6"]
            ICONOS  = ["🏢","🏭","🛒","🏗️","💊","🚛","🍽️","📦","⚙️","🏬"]
            nueva = sb.table("empresas_clientes").insert({
                "nit":         nit,
                "razon_social": nombre,
                "ciudad":      ciudad,
                "sector":      "General",
                "color":       random.choice(COLORES),
                "icono":       random.choice(ICONOS),
            }).execute()
            empresa_id = nueva.data[0]["id"] if nueva.data else None

            if not empresa_id:
                edit_message("❌ Error creando la empresa. Inténtalo manualmente en ContaBot.")
                return jsonify({"ok": True})

            # Registrar la factura pendiente
            from datetime import datetime as dt
            numero = datos.get("numero", "")
            ya = sb.table("facturas_gastos").select("id").eq("empresa_id", empresa_id).eq("numero", numero).execute()
            if not ya.data and numero:
                sb.table("facturas_gastos").insert({
                    "empresa_id":       empresa_id,
                    "numero":           numero,
                    "cufe":             datos.get("cufe", ""),
                    "fecha":            datos.get("fecha") or dt.today().strftime("%Y-%m-%d"),
                    "proveedor_nit":    datos.get("proveedor_nit", ""),
                    "proveedor_nombre": datos.get("proveedor_nombre", ""),
                    "proveedor_ciudad": datos.get("proveedor_ciudad", ""),
                    "subtotal":         float(datos.get("subtotal") or 0),
                    "iva":              float(datos.get("iva") or 0),
                    "total_factura":    float(datos.get("total_factura") or 0),
                    "valor_neto":       float(datos.get("valor_neto") or datos.get("total_factura") or 0),
                    "estado":           "pendiente",
                    "fuente":           fuente,
                }).execute()

            # Limpiar pendiente
            sb.table("empresas_pendientes").delete().eq("id", pendiente_id).execute()

            edit_message(
                f"✅ *Empresa creada y factura registrada*\n\n"
                f"🏢 *{nombre}*\n"
                f"🔢 NIT: `{nit}`\n"
                f"📄 Factura N° {numero or '—'}\n\n"
                f"Ya aparece en el dashboard de ContaBot."
            )
        except Exception as ex:
            print(f"[webhook] Error confirmando empresa: {ex}")
            edit_message(f"❌ Error interno: {ex}")

    elif data.startswith("ignorar_empresa:"):
        pendiente_id = data.split(":", 1)[1]
        answer("Ignorado")
        try:
            row = sb.table("empresas_pendientes").select("nit,razon_social").eq("id", pendiente_id).execute().data
            nombre = row[0]["razon_social"] if row else "desconocida"
            nit    = row[0]["nit"] if row else "—"
            sb.table("empresas_pendientes").delete().eq("id", pendiente_id).execute()
            edit_message(f"🗑️ Factura de *{nombre}* (NIT `{nit}`) ignorada y eliminada.")
        except Exception as ex:
            print(f"[webhook] Error ignorando empresa: {ex}")

    return jsonify({"ok": True})


# ── Cron jobs (APScheduler) ───────────────────────────────────────────────────

def _cron_gmail():
    """Escanea Gmail y registra facturas nuevas."""
    try:
        sys.path.insert(0, SCRIPTS_DIR)
        from gmail_facturas import escanear_inbox
        empresas = sb.table("empresas_clientes").select("id").execute().data
        for e in empresas:
            escanear_inbox(empresa_id=e["id"], max_correos=50)
    except Exception as ex:
        print(f"[cron] Gmail error: {ex}")

def _cron_obligaciones():
    """Notifica por Telegram las obligaciones que vencen en 7 días."""
    try:
        empresas = sb.table("empresas_clientes").select("id,nit,razon_social").execute().data
        proximas = obligaciones_proximas(empresas, dias=7)
        if not proximas:
            return
        token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return
        import urllib.request, json as _json
        lineas = ["*Obligaciones tributarias — próximos 7 días*\n"]
        for p in proximas:
            ob   = p["obligacion"]
            dias = p["dias_restantes"]
            emoji = "🔴" if dias <= 2 else "🟡"
            lineas.append(f"{emoji} *{ob['tipo']}* — {p['empresa']}\n   {ob['periodo']} | Vence {ob['vencimiento']} ({dias}d)")
        payload = _json.dumps({
            "chat_id": chat_id, "text": "\n".join(lineas), "parse_mode": "Markdown"
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as ex:
        print(f"[cron] Obligaciones error: {ex}")

def _iniciar_scheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(_cron_gmail,        "interval", hours=2,  id="gmail")
        scheduler.add_job(_cron_obligaciones, "interval", hours=24, id="obligaciones")
        scheduler.start()
        print("[cron] Scheduler iniciado: Gmail cada 2h, obligaciones cada 24h")
    except ImportError:
        print("[cron] APScheduler no instalado — cron desactivado")
    except Exception as ex:
        print(f"[cron] Error iniciando scheduler: {ex}")


def _migrar_tablas():
    """Crea tablas necesarias si no existen (usa SQL via Supabase RPC si está disponible)."""
    try:
        # Verificar si empresas_pendientes existe intentando hacer un select
        sb.table("empresas_pendientes").select("id").limit(1).execute()
    except Exception:
        # La tabla no existe — intentar crearla via RPC (si existe la función)
        try:
            sb.rpc("exec_sql", {"sql": (
                "CREATE TABLE IF NOT EXISTS empresas_pendientes ("
                "  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,"
                "  nit TEXT,"
                "  razon_social TEXT,"
                "  ciudad TEXT,"
                "  factura_data JSONB,"
                "  fuente TEXT,"
                "  created_at TIMESTAMPTZ DEFAULT NOW()"
                ");"
            )}).execute()
            print("[migración] Tabla empresas_pendientes creada.")
        except Exception as ex:
            print(f"[migración] No se pudo crear empresas_pendientes automáticamente: {ex}")
            print("[migración] Crea la tabla manualmente en Supabase SQL Editor:")
            print("  CREATE TABLE IF NOT EXISTS empresas_pendientes (")
            print("    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,")
            print("    nit TEXT, razon_social TEXT, ciudad TEXT,")
            print("    factura_data JSONB, fuente TEXT,")
            print("    created_at TIMESTAMPTZ DEFAULT NOW()")
            print("  );")


if __name__ == "__main__":
    port    = int(os.environ.get("PORT", 5000))
    is_local = port == 5000
    if is_local:
        import webbrowser, threading
        print("\n  ContaBot Demo — http://localhost:5000\n")
        threading.Timer(1.2, lambda: webbrowser.open("http://localhost:5000")).start()
    _migrar_tablas()
    _iniciar_scheduler()
    app.run(debug=False, host="0.0.0.0", port=port)
