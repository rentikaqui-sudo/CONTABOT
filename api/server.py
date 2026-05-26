"""
ContaBot — Flask API multi-empresa
El contador gestiona 6 empresas clientes desde un solo panel.
"""

import os, sqlite3, json, functools, re
from datetime import date, timedelta
from flask import Flask, jsonify, send_from_directory, request, session, redirect

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH  = os.path.join(BASE_DIR, "data", "demo.db")
UI_DIR   = os.path.join(BASE_DIR, "ui")

app = Flask(__name__, static_folder=UI_DIR)
app.secret_key = "contabot-demo-2026-key-x7f"


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
    conn = db()
    empresas = conn.execute("SELECT * FROM empresas_clientes ORDER BY id").fetchall()
    resultado = []
    for e in empresas:
        eid = e["id"]

        v = conn.execute("""
            SELECT COUNT(*) n, SUM(valor_neto) neto,
                   SUM(CASE WHEN estado='PENDIENTE' THEN valor_neto ELSE 0 END) por_cobrar,
                   SUM(CASE WHEN estado LIKE 'VENCIDA%' THEN valor_neto ELSE 0 END) vencido,
                   SUM(CASE WHEN estado='PAGADA' THEN valor_neto ELSE 0 END) cobrado,
                   SUM(CASE WHEN estado LIKE 'VENCIDA%' THEN 1 ELSE 0 END) n_vencidas,
                   SUM(CASE WHEN estado='POR_VENCER' THEN 1 ELSE 0 END) n_por_vencer
            FROM facturas_venta WHERE empresa_id=?
        """, (eid,)).fetchone()

        g = conn.execute("""
            SELECT COUNT(*) n, SUM(valor_neto) neto,
                   SUM(CASE WHEN estado='PENDIENTE' THEN valor_neto ELSE 0 END) por_pagar,
                   SUM(CASE WHEN estado='PAGADA' THEN valor_neto ELSE 0 END) pagado
            FROM facturas_gastos WHERE empresa_id=?
        """, (eid,)).fetchone()

        alertas = (v["n_vencidas"] or 0) + (v["n_por_vencer"] or 0)
        semaforo = "verde"
        if (v["n_vencidas"] or 0) >= 2:
            semaforo = "rojo"
        elif alertas > 0:
            semaforo = "amarillo"

        resultado.append({
            "id":          e["id"],
            "razon_social":e["razon_social"],
            "nit":         e["nit"],
            "sector":      e["sector"],
            "ciudad":      e["ciudad"],
            "contacto":    e["contacto"],
            "color":       e["color"],
            "icono":       e["icono"],
            "semaforo":    semaforo,
            "ventas": {
                "n":          v["n"],
                "neto":       round(v["neto"] or 0),
                "por_cobrar": round(v["por_cobrar"] or 0),
                "vencido":    round(v["vencido"] or 0),
                "cobrado":    round(v["cobrado"] or 0),
                "n_vencidas": v["n_vencidas"] or 0,
                "n_por_vencer": v["n_por_vencer"] or 0,
            },
            "gastos": {
                "n":       g["n"],
                "neto":    round(g["neto"] or 0),
                "por_pagar":round(g["por_pagar"] or 0),
                "pagado":  round(g["pagado"] or 0),
            },
            "alertas": alertas,
        })
    conn.close()
    return jsonify(resultado)


# ── Resumen consolidado del contador ─────────────────────────────────────────

@app.route("/api/resumen")
@login_required
def resumen():
    conn = db()
    v = conn.execute("""
        SELECT COUNT(*) n, SUM(valor_neto) neto,
               SUM(CASE WHEN estado='PENDIENTE' THEN valor_neto ELSE 0 END) por_cobrar,
               SUM(CASE WHEN estado LIKE 'VENCIDA%' THEN valor_neto ELSE 0 END) vencido,
               SUM(CASE WHEN estado LIKE 'VENCIDA%' THEN 1 ELSE 0 END) n_vencidas,
               SUM(CASE WHEN estado='POR_VENCER' THEN 1 ELSE 0 END) n_por_vencer
        FROM facturas_venta
    """).fetchone()
    g = conn.execute("""
        SELECT COUNT(*) n, SUM(valor_neto) neto,
               SUM(CASE WHEN estado='PENDIENTE' THEN valor_neto ELSE 0 END) por_pagar
        FROM facturas_gastos
    """).fetchone()
    n_empresas = conn.execute("SELECT COUNT(*) n FROM empresas_clientes").fetchone()["n"]
    conn.close()
    return jsonify({
        "n_empresas":    n_empresas,
        "total_ventas":  round(v["neto"] or 0),
        "por_cobrar":    round(v["por_cobrar"] or 0),
        "cartera_vencida":round(v["vencido"] or 0),
        "n_vencidas":    v["n_vencidas"] or 0,
        "n_por_vencer":  v["n_por_vencer"] or 0,
        "total_gastos":  round(g["neto"] or 0),
        "por_pagar":     round(g["por_pagar"] or 0),
        "total_facturas":v["n"] + g["n"],
    })


# ── Detalle de una empresa ────────────────────────────────────────────────────

@app.route("/api/empresa/<int:eid>/dashboard")
@login_required
def empresa_dashboard(eid):
    conn = db()
    e  = conn.execute("SELECT * FROM empresas_clientes WHERE id=?", (eid,)).fetchone()
    v  = conn.execute("""
        SELECT COUNT(*) n, SUM(valor_neto) neto,
               SUM(CASE WHEN estado='PENDIENTE' THEN valor_neto ELSE 0 END) por_cobrar,
               SUM(CASE WHEN estado LIKE 'VENCIDA%' THEN valor_neto ELSE 0 END) vencido,
               SUM(CASE WHEN estado='PAGADA' THEN valor_neto ELSE 0 END) cobrado
        FROM facturas_venta WHERE empresa_id=?
    """, (eid,)).fetchone()
    g  = conn.execute("""
        SELECT COUNT(*) n, SUM(valor_neto) neto,
               SUM(CASE WHEN estado='PENDIENTE' THEN valor_neto ELSE 0 END) por_pagar,
               SUM(CASE WHEN estado='PAGADA' THEN valor_neto ELSE 0 END) pagado
        FROM facturas_gastos WHERE empresa_id=?
    """, (eid,)).fetchone()

    ret_v = conn.execute("""
        SELECT SUM(retefuente) rf, SUM(reteiva) ri, SUM(reteica) rc
        FROM facturas_venta WHERE empresa_id=?
    """, (eid,)).fetchone()
    ret_g = conn.execute("""
        SELECT SUM(retefuente) rf, SUM(reteiva) ri, SUM(reteica) rc
        FROM facturas_gastos WHERE empresa_id=?
    """, (eid,)).fetchone()

    conn.close()
    return jsonify({
        "empresa": dict(e),
        "ventas":  {k: round(v[k] or 0) if v[k] is not None else 0 for k in v.keys()},
        "gastos":  {k: round(g[k] or 0) if g[k] is not None else 0 for k in g.keys()},
        "retenciones_ventas": {"retefuente": round(ret_v["rf"] or 0), "reteiva": round(ret_v["ri"] or 0), "reteica": round(ret_v["rc"] or 0)},
        "retenciones_gastos": {"retefuente": round(ret_g["rf"] or 0), "reteiva": round(ret_g["ri"] or 0), "reteica": round(ret_g["rc"] or 0)},
    })


@app.route("/api/empresa/<int:eid>/facturas/venta")
@login_required
def empresa_ventas(eid):
    conn = db()
    rows = conn.execute("""
        SELECT numero, fecha, fecha_vencimiento, cliente_nombre, cliente_ciudad,
               gran_contribuyente, subtotal, iva, retefuente, reteiva, reteica,
               total_factura, valor_neto, estado
        FROM facturas_venta WHERE empresa_id=? ORDER BY fecha DESC
    """, (eid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/empresa/<int:eid>/facturas/gastos")
@login_required
def empresa_gastos(eid):
    conn = db()
    rows = conn.execute("""
        SELECT numero, fecha, fecha_vencimiento, proveedor_nombre, proveedor_ciudad,
               categoria, subtotal, iva, retefuente, reteiva, reteica,
               total_factura, valor_neto, estado
        FROM facturas_gastos WHERE empresa_id=? ORDER BY fecha DESC
    """, (eid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/empresa/<int:eid>/alertas")
@login_required
def empresa_alertas(eid):
    conn = db()
    e    = conn.execute("SELECT razon_social FROM empresas_clientes WHERE id=?", (eid,)).fetchone()
    rows = conn.execute("""
        SELECT numero, cliente_nombre, cliente_ciudad, valor_neto,
               fecha_vencimiento, estado
        FROM facturas_venta
        WHERE empresa_id=? AND (estado LIKE 'VENCIDA%' OR estado='POR_VENCER')
        ORDER BY fecha_vencimiento ASC
    """, (eid,)).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
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
    conn = db()
    rows = conn.execute("""
        SELECT fv.numero, fv.cliente_nombre, fv.valor_neto,
               fv.fecha_vencimiento, fv.estado,
               ec.razon_social as empresa_nombre, ec.color as empresa_color,
               ec.id as empresa_id
        FROM facturas_venta fv
        JOIN empresas_clientes ec ON fv.empresa_id = ec.id
        WHERE fv.estado LIKE 'VENCIDA%' OR fv.estado='POR_VENCER'
        ORDER BY fv.fecha_vencimiento ASC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── Retenciones por cliente (para un empresa dada) ────────────────────────────

@app.route("/api/empresa/<int:eid>/retenciones-por-cliente")
@login_required
def retenciones_por_cliente(eid):
    conn = db()
    rows = conn.execute("""
        SELECT cliente_nombre, cliente_ciudad,
               COUNT(*) n_facturas,
               SUM(retefuente) retefuente,
               SUM(reteiva) reteiva,
               SUM(reteica) reteica,
               SUM(retefuente+reteiva+reteica) total_ret,
               SUM(valor_neto) valor_neto
        FROM facturas_venta
        WHERE empresa_id=?
        GROUP BY cliente_nit
        ORDER BY total_ret DESC
    """, (eid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── Factura manual (papel) ────────────────────────────────────────────────────

@app.route("/api/factura-manual", methods=["POST"])
@login_required
def factura_manual():
    data = request.get_json()
    conn = db()

    fecha     = data.get("fecha", date.today().isoformat())
    dias      = int(data.get("dias_pago", 30))
    fecha_vto = (date.fromisoformat(fecha) + timedelta(days=dias)).isoformat()

    hoy       = date.today()
    vto_date  = date.fromisoformat(fecha_vto)
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
            conn.execute("""
                INSERT OR REPLACE INTO facturas_gastos
                (empresa_id,numero,cufe,fecha,fecha_vencimiento,
                 proveedor_nit,proveedor_nombre,proveedor_ciudad,
                 categoria,subtotal,iva,retefuente,reteiva,reteica,
                 total_factura,valor_neto,estado,archivo_pdf)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                data["empresa_id"], data["numero"], "MANUAL-" + data["numero"],
                fecha, fecha_vto,
                data.get("tercero_nit",""), data.get("tercero_nombre",""), "Manual",
                data.get("categoria","insumos"),
                data["subtotal"], data["iva"], data["retefuente"],
                data["reteiva"], data["reteica"],
                data["total_factura"], data["valor_neto"],
                estado, ""
            ))
        else:
            conn.execute("""
                INSERT OR REPLACE INTO facturas_venta
                (empresa_id,numero,cufe,fecha,fecha_vencimiento,
                 cliente_nit,cliente_nombre,cliente_ciudad,
                 gran_contribuyente,subtotal,iva,retefuente,reteiva,reteica,
                 total_factura,valor_neto,estado,archivo_pdf)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                data["empresa_id"], data["numero"], "MANUAL-" + data["numero"],
                fecha, fecha_vto,
                data.get("tercero_nit",""), data.get("tercero_nombre",""), "Manual",
                0,
                data["subtotal"], data["iva"], data["retefuente"],
                data["reteiva"], data["reteica"],
                data["total_factura"], data["valor_neto"],
                estado, ""
            ))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as ex:
        conn.close()
        return jsonify({"ok": False, "error": str(ex)}), 400


# ── Procesar imagen de factura (QR / OCR) ────────────────────────────────────

@app.route("/api/procesar-imagen", methods=["POST"])
@login_required
def procesar_imagen():
    if "imagen" not in request.files:
        return jsonify({"ok": False, "error": "No se recibió imagen"}), 400

    archivo = request.files["imagen"]
    img_bytes = archivo.read()
    nombre = archivo.filename or "imagen"

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
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return jsonify({"ok": False, "error": "No se pudo leer la imagen. Verifique el formato (JPG, PNG, etc.)"}), 400

    # ── Intentar leer QR ──────────────────────────────────────────────────────
    detector = cv2.QRCodeDetector()
    qr_data, bbox, _ = detector.detectAndDecode(img)

    if qr_data:
        resultado["metodo"] = "qr"
        resultado["raw"] = qr_data
        resultado["datos"] = _parse_dian_qr(qr_data)
        return jsonify(resultado)

    # ── Intentar OCR ─────────────────────────────────────────────────────────
    try:
        import pytesseract
        from PIL import Image as PILImage
        import io

        pil_img = PILImage.open(io.BytesIO(img_bytes))
        texto = pytesseract.image_to_string(pil_img, lang="spa+eng")
        resultado["metodo"] = "ocr"
        resultado["raw"] = texto
        resultado["datos"] = _parse_ocr_texto(texto)
    except ImportError:
        resultado["metodo"] = "sin_ocr"
        resultado["datos"] = {
            "confiabilidad": "N/A",
            "fuente": "No se encontró QR y pytesseract no está instalado",
        }
        resultado["mensaje"] = "No se detectó código QR en la imagen. Instale pytesseract + Tesseract para OCR."
    except Exception as e:
        resultado["metodo"] = "error_ocr"
        resultado["datos"] = {"fuente": "Error en OCR", "confiabilidad": "N/A"}
        resultado["mensaje"] = f"No se pudo extraer texto: {str(e)}"

    return jsonify(resultado)


def _parse_dian_qr(qr_text):
    datos = {"tipo": "url_dian", "url": qr_text}

    cufe = re.search(r'documentkey=([a-f0-9]{96})', qr_text, re.IGNORECASE)
    if cufe:
        datos["cufe"] = cufe.group(1)
        datos["cufe_corto"] = cufe.group(1)[:16] + "..." + cufe.group(1)[-8:]

    datos["fuente"] = "QR de factura electrónica DIAN"
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
        datos["total"] = int(re.sub(r'[.,]', '', m.group(1))[:12])

    m = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4}|\d{4}[/-]\d{2}[/-]\d{2})', texto)
    if m:
        datos["fecha"] = m.group(1)

    m = re.search(r'(?:factura|FV|FC|FE|N[°º])[:\s#-]*([A-Z0-9-]{3,20})', texto, re.IGNORECASE)
    if m:
        datos["numero"] = m.group(1).strip()

    m = re.search(r'CUFE[:\s]*([a-f0-9]{32,})', texto, re.IGNORECASE)
    if m:
        datos["cufe"] = m.group(1)[:96]

    datos["fuente"] = "OCR — reconocimiento óptico de texto"
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

    conn = db()
    e  = conn.execute("SELECT * FROM empresas_clientes WHERE id=?", (eid,)).fetchone()
    vs = conn.execute("SELECT numero,fecha,cliente_nombre,subtotal,iva,retefuente,reteiva,reteica,total_factura,valor_neto,estado FROM facturas_venta  WHERE empresa_id=? ORDER BY fecha", (eid,)).fetchall()
    gs = conn.execute("SELECT numero,fecha,proveedor_nombre,categoria,subtotal,iva,retefuente,reteiva,reteica,total_factura,valor_neto,estado FROM facturas_gastos WHERE empresa_id=? ORDER BY fecha", (eid,)).fetchall()
    vt = conn.execute("SELECT COUNT(*) n,SUM(total_factura) total,SUM(valor_neto) neto,SUM(retefuente) rf,SUM(reteiva) ri,SUM(reteica) rc,SUM(CASE WHEN estado='PENDIENTE' THEN valor_neto ELSE 0 END) por_cobrar,SUM(CASE WHEN estado LIKE 'VENCIDA%' THEN valor_neto ELSE 0 END) vencido FROM facturas_venta  WHERE empresa_id=?", (eid,)).fetchone()
    gt = conn.execute("SELECT COUNT(*) n,SUM(total_factura) total,SUM(valor_neto) neto,SUM(retefuente) rf,SUM(reteiva) ri,SUM(reteica) rc FROM facturas_gastos WHERE empresa_id=?", (eid,)).fetchone()
    conn.close()

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
    utilidad = (vt['neto'] or 0) - (gt['neto'] or 0)
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
        ps(fmt(vt['rf'] or 0),8,True,RED,2), ps(fmt(vt['total'] or 0),8,True,align=2),
        ps(fmt(vt['neto'] or 0),8,True,BLUE,2), ps('',7)])
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
        ps(fmt(gt['rf'] or 0),8,True,RED,2), ps(fmt(gt['total'] or 0),8,True,align=2),
        ps(fmt(gt['neto'] or 0),8,True,RED,2)])
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
         ps(fmt(gt['rf'] or 0),9,align=2), ps(fmt(gt['ri'] or 0),9,align=2), ps(fmt(gt['rc'] or 0),9,align=2),
         ps(fmt((gt['rf'] or 0)+(gt['ri'] or 0)+(gt['rc'] or 0)),9,True,RED,2)],
        [ps('Sufridas (retenidas por clientes)',9),
         ps(fmt(vt['rf'] or 0),9,align=2), ps(fmt(vt['ri'] or 0),9,align=2), ps(fmt(vt['rc'] or 0),9,align=2),
         ps(fmt((vt['rf'] or 0)+(vt['ri'] or 0)+(vt['rc'] or 0)),9,True,BLUE,2)],
    ]
    saldo = ((gt['rf'] or 0)+(gt['ri'] or 0)+(gt['rc'] or 0)) - ((vt['rf'] or 0)+(vt['ri'] or 0)+(vt['rc'] or 0))
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
    conn = db()
    emps = conn.execute("SELECT id,razon_social,nit,color FROM empresas_clientes ORDER BY id").fetchall()
    hoy  = date.today()
    # Fecha límite declaración retefuente: día 12 del mes siguiente
    mes_sig = hoy.month % 12 + 1
    anio_sig = hoy.year + (1 if hoy.month == 12 else 0)
    fecha_limite = date(anio_sig, mes_sig, 12)
    dias = (fecha_limite - hoy).days

    resultado = []
    total_global = 0
    for e in emps:
        g = conn.execute("SELECT SUM(retefuente) rf,SUM(reteiva) ri,SUM(reteica) rc FROM facturas_gastos WHERE empresa_id=?", (e['id'],)).fetchone()
        v = conn.execute("SELECT SUM(retefuente) rf,SUM(reteiva) ri,SUM(reteica) rc FROM facturas_venta  WHERE empresa_id=?", (e['id'],)).fetchone()
        rf = round(g['rf'] or 0); ri = round(g['ri'] or 0); rc = round(g['rc'] or 0)
        total = rf + ri + rc
        total_global += total
        resultado.append({
            'empresa_id': e['id'], 'razon_social': e['razon_social'],
            'nit': e['nit'], 'color': e['color'],
            'retefuente': rf, 'reteiva': ri, 'reteica': rc, 'total': total,
            'sufrido_retefuente': round(v['rf'] or 0),
            'fecha_limite': fecha_limite.isoformat(), 'dias': dias,
            'estado': 'VENCIDA' if dias < 0 else ('HOY' if dias == 0 else 'PENDIENTE'),
        })
    conn.close()
    return jsonify({
        'fecha_limite': fecha_limite.isoformat(), 'dias': dias,
        'mes': hoy.strftime('%B %Y'), 'empresas': resultado,
        'total_consolidado': total_global,
    })


# ── Flujo de caja proyectado 60 días ─────────────────────────────────────────

@app.route("/api/empresa/<int:eid>/flujo-caja")
@login_required
def flujo_caja(eid):
    conn = db()
    hoy = date.today()
    ventas = conn.execute("""
        SELECT fecha_vencimiento, valor_neto FROM facturas_venta
        WHERE empresa_id=? AND estado IN ('PENDIENTE','POR_VENCER') AND fecha_vencimiento >= ?
    """, (eid, hoy.isoformat())).fetchall()
    gastos = conn.execute("""
        SELECT fecha_vencimiento, valor_neto FROM facturas_gastos
        WHERE empresa_id=? AND estado IN ('PENDIENTE','POR_VENCER') AND fecha_vencimiento >= ?
    """, (eid, hoy.isoformat())).fetchall()
    cartera = conn.execute("""
        SELECT SUM(valor_neto) total FROM facturas_venta WHERE empresa_id=? AND estado LIKE 'VENCIDA%'
    """, (eid,)).fetchone()
    conn.close()

    semanas = []
    for i in range(8):
        ini = hoy + timedelta(days=i * 7)
        fin = ini + timedelta(days=6)
        ing = sum(r['valor_neto'] or 0 for r in ventas
                  if ini <= date.fromisoformat(r['fecha_vencimiento']) <= fin)
        egr = sum(r['valor_neto'] or 0 for r in gastos
                  if ini <= date.fromisoformat(r['fecha_vencimiento']) <= fin)
        semanas.append({
            'label': f"{ini.strftime('%d/%m')}–{fin.strftime('%d/%m')}",
            'ingresos': round(ing), 'egresos': round(egr), 'neto': round(ing - egr),
        })
    return jsonify({'semanas': semanas, 'cartera_vencida': round(cartera['total'] or 0)})


# ── Export Excel ───────────────────────────────────────────────────────────────

@app.route("/api/empresa/<int:eid>/informe-excel")
@login_required
def informe_excel(eid):
    try:
        import pandas as pd
        import openpyxl  # noqa: F401
    except ImportError:
        return jsonify({"error": "Instale openpyxl: pip install openpyxl"}), 500
    import io
    from flask import make_response

    conn = db()
    e  = conn.execute("SELECT * FROM empresas_clientes WHERE id=?", (eid,)).fetchone()
    vs = conn.execute("""
        SELECT numero 'N° Factura', fecha 'Fecha', fecha_vencimiento 'Vencimiento',
               cliente_nombre 'Cliente', cliente_ciudad 'Ciudad',
               subtotal 'Subtotal', iva 'IVA',
               retefuente 'Retefuente', reteiva 'ReteIVA', reteica 'ReteICA',
               total_factura 'Total Factura', valor_neto 'Neto a Cobrar', estado 'Estado'
        FROM facturas_venta WHERE empresa_id=? ORDER BY fecha
    """, (eid,)).fetchall()
    gs = conn.execute("""
        SELECT numero 'N° Factura', fecha 'Fecha', fecha_vencimiento 'Vencimiento',
               proveedor_nombre 'Proveedor', proveedor_ciudad 'Ciudad', categoria 'Categoria',
               subtotal 'Subtotal', iva 'IVA',
               retefuente 'Retefuente', reteiva 'ReteIVA', reteica 'ReteICA',
               total_factura 'Total Factura', valor_neto 'Neto a Pagar', estado 'Estado'
        FROM facturas_gastos WHERE empresa_id=? ORDER BY fecha
    """, (eid,)).fetchall()
    rets = conn.execute("""
        SELECT cliente_nombre 'Cliente', COUNT(*) 'N Facturas',
               SUM(retefuente) 'Retefuente', SUM(reteiva) 'ReteIVA',
               SUM(reteica) 'ReteICA',
               SUM(retefuente+reteiva+reteica) 'Total Retenciones'
        FROM facturas_venta WHERE empresa_id=?
        GROUP BY cliente_nit ORDER BY SUM(retefuente+reteiva+reteica) DESC
    """, (eid,)).fetchall()
    conn.close()

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        pd.DataFrame([dict(r) for r in vs]).to_excel(writer, sheet_name='Ventas', index=False)
        pd.DataFrame([dict(r) for r in gs]).to_excel(writer, sheet_name='Gastos', index=False)
        pd.DataFrame([dict(r) for r in rets]).to_excel(writer, sheet_name='Retenciones', index=False)

    buf.seek(0)
    resp = make_response(buf.read())
    resp.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    nombre = re.sub(r'[^a-zA-Z0-9]', '_', e['razon_social'])[:28]
    resp.headers['Content-Disposition'] = f'attachment; filename="ContaBot_{nombre}_2026.xlsx"'
    return resp


# ── Marcar factura como pagada ─────────────────────────────────────────────────

@app.route("/api/factura/<tipo>/<path:numero>/empresa/<int:eid>/pagar", methods=["POST"])
@login_required
def marcar_pagada(tipo, numero, eid):
    if tipo not in ("venta", "gasto"):
        return jsonify({"ok": False, "error": "Tipo inválido"}), 400
    tabla = "facturas_venta" if tipo == "venta" else "facturas_gastos"
    conn = db()
    conn.execute(f"UPDATE {tabla} SET estado='PAGADA' WHERE numero=? AND empresa_id=?", (numero, eid))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


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

    monto_col = next((c for c in df.columns if any(k in c for k in ['monto','valor','importe','credito','credito','credit','debit','debito'])), None)
    fecha_col = next((c for c in df.columns if any(k in c for k in ['fecha','date','dia'])), None)
    desc_col  = next((c for c in df.columns if any(k in c for k in ['descripcion','desc','concepto','referencia','detail','concepto'])), None)

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

    conn = db()
    ventas = conn.execute("""
        SELECT numero, valor_neto, cliente_nombre, fecha_vencimiento, estado
        FROM facturas_venta WHERE empresa_id=? AND estado NOT IN ('PAGADA')
    """, (eid,)).fetchall()
    gastos = conn.execute("""
        SELECT numero, valor_neto, proveedor_nombre cliente_nombre, fecha_vencimiento, estado
        FROM facturas_gastos WHERE empresa_id=? AND estado NOT IN ('PAGADA')
    """, (eid,)).fetchall()
    conn.close()

    todas = list(ventas) + list(gastos)
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
                "extracto_monto": int(monto),
                "extracto_fecha": fecha,
                "extracto_desc":  desc[:60],
                "factura_numero": match['numero'],
                "factura_tercero":match['cliente_nombre'],
                "factura_neto":   int(match['valor_neto'] or 0),
                "diferencia":     int(abs(monto - (match['valor_neto'] or 0))),
                "tipo":           "exacto" if abs(monto - (match['valor_neto'] or 0)) < 1000 else "aproximado",
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    is_local = port == 5000
    if is_local:
        import webbrowser, threading
        print("\n  ContaBot Demo — http://localhost:5000\n")
        threading.Timer(1.2, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(debug=False, host="0.0.0.0", port=port)
