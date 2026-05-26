"""
Genera ~54 facturas colombianas distribuidas entre 6 empresas clientes
del Estudio Contable Aristizábal & Asociados.
~9 facturas por empresa (5-6 ventas + 3-4 gastos).
"""

import sys, os, random
sys.path.insert(0, os.path.dirname(__file__))

from datos_colombia import (
    ESTUDIO, EMPRESAS_CLIENTES, CLIENTES_POR_EMPRESA,
    PROVEEDORES_POR_EMPRESA, PRODUCTOS_POR_EMPRESA, RETENCIONES_GASTO,
    TASAS, fecha_aleatoria, generar_cufe, formatear_pesos
)
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from datetime import timedelta
import sqlite3

BASE_DIR  = os.path.dirname(os.path.dirname(__file__))
DB_PATH   = os.path.join(BASE_DIR, "data", "demo.db")

AZUL_OSCURO = colors.HexColor("#1e3a5f")
AZUL_MEDIO  = colors.HexColor("#2563eb")
GRIS_CLARO  = colors.HexColor("#f8fafc")
GRIS_BORDE  = colors.HexColor("#e2e8f0")
TEXTO       = colors.HexColor("#1e293b")


def carpeta_empresa(empresa, tipo):
    nombre = empresa["razon_social"].split()[0].lower()
    path = os.path.join(BASE_DIR, "data", f"empresa_{empresa['id']}_{nombre}", tipo)
    os.makedirs(path, exist_ok=True)
    return path


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS empresas_clientes (
            id INTEGER PRIMARY KEY,
            razon_social TEXT, nit TEXT, sector TEXT, ciudad TEXT,
            direccion TEXT, contacto TEXT, email TEXT, telefono TEXT,
            regimen TEXT, color TEXT, icono TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS facturas_venta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            numero TEXT UNIQUE, cufe TEXT,
            fecha TEXT, fecha_vencimiento TEXT,
            cliente_nit TEXT, cliente_nombre TEXT, cliente_ciudad TEXT,
            gran_contribuyente INTEGER,
            subtotal REAL, iva REAL, retefuente REAL, reteiva REAL, reteica REAL,
            total_factura REAL, valor_neto REAL, estado TEXT, archivo_pdf TEXT,
            FOREIGN KEY(empresa_id) REFERENCES empresas_clientes(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS facturas_gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            numero TEXT UNIQUE, cufe TEXT,
            fecha TEXT, fecha_vencimiento TEXT,
            proveedor_nit TEXT, proveedor_nombre TEXT, proveedor_ciudad TEXT,
            categoria TEXT,
            subtotal REAL, iva REAL, retefuente REAL, reteiva REAL, reteica REAL,
            total_factura REAL, valor_neto REAL, estado TEXT, archivo_pdf TEXT,
            FOREIGN KEY(empresa_id) REFERENCES empresas_clientes(id)
        )
    """)
    conn.commit()
    return conn


def estilos():
    return {
        "negrita": ParagraphStyle("nb", fontName="Helvetica-Bold", fontSize=8, textColor=TEXTO, leading=11),
        "normal":  ParagraphStyle("nm", fontName="Helvetica", fontSize=8, textColor=TEXTO, leading=11),
        "pequeño": ParagraphStyle("pq", fontName="Helvetica", fontSize=7, textColor=colors.HexColor("#64748b"), leading=10),
        "blanco":  ParagraphStyle("bl", fontName="Helvetica-Bold", fontSize=12, textColor=colors.white),
        "blanco_r":ParagraphStyle("blr",fontName="Helvetica-Bold", fontSize=14, textColor=colors.white, alignment=TA_RIGHT),
    }


def encabezado(s, emisor, receptor, numero, fecha, fecha_vto, cufe, es_venta):
    tipo_doc = "FACTURA ELECTRÓNICA DE VENTA" if es_venta else "FACTURA ELECTRÓNICA DE COMPRA"
    header = Table([[Paragraph(f"<font color='white'><b>{tipo_doc}</b></font>", s["blanco"]),
                     Paragraph(f"<font color='white'><b>{numero}</b></font>", s["blanco_r"])]],
                   colWidths=[11*cm, 7*cm])
    header.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),AZUL_OSCURO),
        ("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10),
        ("LEFTPADDING",(0,0),(0,-1),12),("RIGHTPADDING",(-1,0),(-1,-1),12),
    ]))

    emisor_rows = [[p] for p in [
        Paragraph(f"<b>{emisor['razon_social']}</b>", s["negrita"]),
        Paragraph(f"NIT: {emisor['nit']}", s["normal"]),
        Paragraph(emisor.get("direccion", emisor.get("ciudad","")), s["normal"]),
        Paragraph(f"Tel: {emisor.get('telefono','')}", s["normal"]),
        Paragraph(emisor.get("email",""), s["normal"]),
        Paragraph(f"Regimen: {emisor.get('regimen','Responsable de IVA')}", s["pequeño"]),
        Paragraph(f"Resolucion DIAN: {emisor.get('resolucion_dian','N/A')}", s["pequeño"]),
    ]]
    emisor_t = Table(emisor_rows, colWidths=[9*cm])
    emisor_t.setStyle(TableStyle([("TOPPADDING",(0,0),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-1),1),("LEFTPADDING",(0,0),(-1,-1),0)]))

    datos_t = Table([
        [Paragraph("<b>Fecha emision:</b>", s["normal"]), Paragraph(fecha.strftime("%d/%m/%Y"), s["normal"])],
        [Paragraph("<b>Vencimiento:</b>",   s["normal"]), Paragraph(fecha_vto.strftime("%d/%m/%Y"), s["normal"])],
        [Paragraph("<b>Forma de pago:</b>", s["normal"]), Paragraph("Credito 30 dias", s["normal"])],
        [Paragraph("<b>Moneda:</b>",        s["normal"]), Paragraph("COP", s["normal"])],
    ], colWidths=[4*cm, 4*cm])
    datos_t.setStyle(TableStyle([("FONTSIZE",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)]))

    top = Table([[emisor_t, datos_t]], colWidths=[10*cm, 8*cm])
    top.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP")]))

    # Receptor
    tipo_receptor = "CLIENTE" if es_venta else "PROVEEDOR"
    rec_hdr = Table([[Paragraph(f"<font color='white'><b>DATOS DEL {tipo_receptor}</b></font>",
                                ParagraphStyle("rh", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white))]],
                    colWidths=[18*cm])
    rec_hdr.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),AZUL_MEDIO),
                                  ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),("LEFTPADDING",(0,0),(-1,-1),8)]))

    ciudad_r = receptor.get("ciudad", receptor.get("direccion","Bogota").split(",")[-1].strip())
    rec_data = Table([
        [Paragraph(f"<b>Razon Social:</b> {receptor['razon_social']}", s["normal"]),
         Paragraph(f"<b>NIT:</b> {receptor['nit']}", s["normal"])],
        [Paragraph(f"<b>Ciudad:</b> {ciudad_r}", s["normal"]),
         Paragraph(f"<b>Email:</b> {receptor.get('email','')}", s["normal"])],
        [Paragraph(f"<b>Telefono:</b> {receptor.get('telefono','')}", s["normal"]),
         Paragraph(f"<b>Regimen:</b> {receptor.get('regimen','Responsable de IVA')}", s["normal"])],
    ], colWidths=[10*cm, 8*cm])
    rec_data.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),GRIS_CLARO),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),8),("GRID",(0,0),(-1,-1),0.3,GRIS_BORDE),
    ]))

    return [header, Spacer(1,0.3*cm), top, Spacer(1,0.3*cm),
            HRFlowable(width="100%",thickness=1,color=AZUL_MEDIO), Spacer(1,0.2*cm),
            rec_hdr, rec_data, Spacer(1,0.4*cm),
            Paragraph(f"<b>CUFE:</b> {cufe[:48]}...", s["pequeño"]),
            Spacer(1,0.3*cm)]


def tabla_items(s, items):
    data = [["#","Descripcion","Und.","Cant.","Vr. Unitario","Vr. Total"]]
    for i, it in enumerate(items, 1):
        data.append([str(i), it["descripcion"], it["unidad"],
                     str(it["cantidad"]), formatear_pesos(it["precio_unitario"]),
                     formatear_pesos(it["total_item"])])
    t = Table(data, colWidths=[0.8*cm,7.5*cm,1.5*cm,1.2*cm,3*cm,3*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),AZUL_OSCURO),("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,GRIS_CLARO]),
        ("GRID",(0,0),(-1,-1),0.3,GRIS_BORDE),("ALIGN",(3,0),(-1,-1),"RIGHT"),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    return [t, Spacer(1,0.3*cm)]


def tabla_totales(s, subtotal, iva_v, retefuente, reteiva, reteica, total, neto):
    filas = [["Subtotal:", formatear_pesos(subtotal)],
             [f"IVA ({int(iva_v/subtotal*100) if subtotal else 0}%):", formatear_pesos(iva_v)]]
    if retefuente > 0: filas.append(["(-) Retefuente:", f"({formatear_pesos(retefuente)})"])
    if reteiva    > 0: filas.append(["(-) ReteIVA 15%:", f"({formatear_pesos(reteiva)})"])
    if reteica    > 0: filas.append(["(-) ReteICA 4.14%:", f"({formatear_pesos(reteica)})"])
    filas += [["Total Factura:", formatear_pesos(total)],
              ["VALOR NETO A PAGAR:", formatear_pesos(neto)]]

    inner = Table(filas, colWidths=[4.5*cm, 3.5*cm])
    style = [("FONTSIZE",(0,0),(-1,-1),8),("ALIGN",(1,0),(1,-1),"RIGHT"),
             ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
             ("LINEBELOW",(0,-2),(-1,-2),0.5,AZUL_MEDIO),
             ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("FONTSIZE",(0,-1),(-1,-1),10),
             ("TEXTCOLOR",(0,-1),(-1,-1),AZUL_OSCURO),("BACKGROUND",(0,-1),(-1,-1),GRIS_CLARO)]
    for i, f in enumerate(filas):
        if "(-)" in str(f[0]):
            style.append(("TEXTCOLOR",(0,i),(-1,i),colors.HexColor("#dc2626")))
    inner.setStyle(TableStyle(style))

    outer = Table([["", inner]], colWidths=[10*cm, 8*cm])
    outer.setStyle(TableStyle([("ALIGN",(1,0),(1,0),"RIGHT"),("VALIGN",(0,0),(-1,-1),"TOP")]))
    return [outer, Spacer(1,0.5*cm)]


def pie(s, cufe):
    return [
        HRFlowable(width="100%",thickness=0.5,color=GRIS_BORDE), Spacer(1,0.2*cm),
        Paragraph("Documento validado ante la DIAN. Conserve como soporte de declaracion de renta.",
                  ParagraphStyle("pie", fontName="Helvetica", fontSize=6.5,
                                 textColor=colors.HexColor("#94a3b8"), alignment=TA_CENTER)),
        Paragraph(f"CUFE: {cufe}",
                  ParagraphStyle("cufe", fontName="Helvetica", fontSize=6,
                                 textColor=colors.HexColor("#cbd5e1"), alignment=TA_CENTER)),
    ]


def calcular_venta(items, gran_contribuyente, iva_rate):
    subtotal = sum(i["total_item"] for i in items)
    iva_v    = round(subtotal * iva_rate)
    total    = subtotal + iva_v
    ret_base = subtotal if subtotal >= 892000 else 0
    retefuente = round(ret_base * TASAS["retefuente_compras"])
    reteiva    = round(iva_v * TASAS["reteiva"]) if gran_contribuyente and iva_v > 0 else 0
    reteica    = round(subtotal * TASAS["reteica_bogota"])
    neto       = total - retefuente - reteiva - reteica
    return subtotal, iva_v, retefuente, reteiva, reteica, total, neto


def calcular_gasto(subtotal, categoria):
    t = RETENCIONES_GASTO.get(categoria, RETENCIONES_GASTO["servicios"])
    iva_v      = round(subtotal * t["iva"])
    total      = subtotal + iva_v
    ret_base   = subtotal if subtotal >= 892000 else 0
    retefuente = round(ret_base * t["retefuente"])
    reteiva    = round(iva_v * t["reteiva"]) if t["reteiva"] > 0 else 0
    reteica    = round(subtotal * t["reteica"])
    neto       = total - retefuente - reteiva - reteica
    return iva_v, retefuente, reteiva, reteica, total, neto


def estado_factura(fecha_vto, hoy):
    if fecha_vto < hoy:
        dias = (hoy - fecha_vto).days
        return f"VENCIDA ({dias} dias)"
    if (fecha_vto - hoy).days <= 7:
        return "POR_VENCER"
    return random.choice(["PAGADA","PAGADA","PENDIENTE"])


def generar_venta(conn, empresa, cliente, numero, hoy):
    productos = PRODUCTOS_POR_EMPRESA[empresa["id"]]
    n_items   = random.randint(1, min(3, len(productos)))
    muestras  = random.sample(productos, n_items)
    items = []
    for p in muestras:
        cantidad = random.randint(1, 30) if p["precio_base"] < 100000 else random.randint(1, 5)
        precio   = int(p["precio_base"] * random.uniform(0.92, 1.08))
        items.append({"descripcion": p["descripcion"], "unidad": p["unidad"],
                      "cantidad": cantidad, "precio_unitario": precio,
                      "total_item": precio * cantidad})

    iva_rate = muestras[0]["iva"]
    subtotal, iva_v, retefuente, reteiva, reteica, total, neto = \
        calcular_venta(items, cliente.get("gran_contribuyente", False), iva_rate)

    fecha     = fecha_aleatoria()
    fecha_vto = fecha + timedelta(days=30)
    cufe      = generar_cufe()
    carpeta   = carpeta_empresa(empresa, "ventas")
    archivo   = f"{numero}.pdf"
    ruta      = os.path.join(carpeta, archivo)

    s = estilos()
    doc = SimpleDocTemplate(ruta, pagesize=letter,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    elems = (encabezado(s, empresa, cliente, numero, fecha, fecha_vto, cufe, True)
             + tabla_items(s, items)
             + tabla_totales(s, subtotal, iva_v, retefuente, reteiva, reteica, total, neto)
             + pie(s, cufe))
    doc.build(elems)

    conn.execute("""
        INSERT OR REPLACE INTO facturas_venta
        (empresa_id,numero,cufe,fecha,fecha_vencimiento,cliente_nit,cliente_nombre,
         cliente_ciudad,gran_contribuyente,subtotal,iva,retefuente,reteiva,reteica,
         total_factura,valor_neto,estado,archivo_pdf)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (empresa["id"], numero, cufe, fecha.isoformat(), fecha_vto.isoformat(),
          cliente["nit"], cliente["razon_social"], cliente["ciudad"],
          int(cliente.get("gran_contribuyente", False)),
          subtotal, iva_v, retefuente, reteiva, reteica, total, neto,
          estado_factura(fecha_vto, hoy), archivo))
    conn.commit()
    print(f"  V {numero:15s} | {empresa['razon_social'][:28]:28s} | {cliente['razon_social'][:28]:28s} | {formatear_pesos(neto)}")


def generar_gasto(conn, empresa, proveedor, numero, hoy):
    categoria = proveedor["categoria"]
    rangos = {
        "insumos":(200000,4000000), "transporte":(300000,2500000),
        "servicios":(400000,3500000), "telecomunicaciones":(200000,700000),
        "seguros":(900000,4000000), "arrendamiento":(2500000,7000000),
        "publicidad":(500000,3000000), "honorarios":(1200000,9000000),
        "tecnologia":(500000,6000000), "seguridad":(700000,2500000),
        "servicios_publicos":(90000,500000),
    }
    lo, hi   = rangos.get(categoria, (300000, 3000000))
    subtotal = random.randint(lo // 1000, hi // 1000) * 1000
    iva_v, retefuente, reteiva, reteica, total, neto = calcular_gasto(subtotal, categoria)

    descripciones = {
        "insumos":"Compra de insumos y materiales","transporte":"Servicio de transporte",
        "servicios":"Servicios de mantenimiento","telecomunicaciones":"Internet y telefonia",
        "seguros":"Prima de seguro corporativo","arrendamiento":"Canon de arrendamiento",
        "publicidad":"Servicio de publicidad digital","honorarios":"Honorarios profesionales",
        "tecnologia":"Licencias y soporte tecnologico","seguridad":"Servicio de seguridad privada",
        "servicios_publicos":"Servicio publico",
    }
    unidades = {"insumos":"Global","seguros":"Poliza","arrendamiento":"Mes"}
    item = {"descripcion": descripciones.get(categoria,"Servicio prestado"),
            "unidad": unidades.get(categoria,"Servicio"),
            "cantidad": 1, "precio_unitario": subtotal, "total_item": subtotal}

    fecha     = fecha_aleatoria()
    fecha_vto = fecha + timedelta(days=random.choice([15,30,45]))
    cufe      = generar_cufe()
    carpeta   = carpeta_empresa(empresa, "gastos")
    archivo   = f"{numero}.pdf"
    ruta      = os.path.join(carpeta, archivo)

    s = estilos()
    doc = SimpleDocTemplate(ruta, pagesize=letter,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    elems = (encabezado(s, proveedor, empresa, numero, fecha, fecha_vto, cufe, False)
             + tabla_items(s, [item])
             + tabla_totales(s, subtotal, iva_v, retefuente, reteiva, reteica, total, neto)
             + pie(s, cufe))
    doc.build(elems)

    # Estado gasto
    if fecha_vto < hoy:
        estado = "PAGADA" if random.random() > 0.25 else "VENCIDA"
    else:
        estado = random.choice(["PENDIENTE","PENDIENTE","PAGADA"])

    conn.execute("""
        INSERT OR REPLACE INTO facturas_gastos
        (empresa_id,numero,cufe,fecha,fecha_vencimiento,proveedor_nit,proveedor_nombre,
         proveedor_ciudad,categoria,subtotal,iva,retefuente,reteiva,reteica,
         total_factura,valor_neto,estado,archivo_pdf)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (empresa["id"], numero, cufe, fecha.isoformat(), fecha_vto.isoformat(),
          proveedor["nit"], proveedor["razon_social"], proveedor["ciudad"],
          categoria, subtotal, iva_v, retefuente, reteiva, reteica, total, neto,
          estado, archivo))
    conn.commit()
    print(f"  G {numero:15s} | {empresa['razon_social'][:28]:28s} | {proveedor['razon_social'][:28]:28s} | {formatear_pesos(neto)}")


def main():
    print("\n=== ContaBot — Generando facturas para 6 empresas clientes ===\n")

    conn = init_db()
    conn.execute("DELETE FROM facturas_venta")
    conn.execute("DELETE FROM facturas_gastos")
    conn.execute("DELETE FROM empresas_clientes")
    conn.commit()

    # Insertar empresas clientes
    for e in EMPRESAS_CLIENTES:
        conn.execute("""
            INSERT INTO empresas_clientes (id,razon_social,nit,sector,ciudad,
            direccion,contacto,email,telefono,regimen,color,icono)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (e["id"],e["razon_social"],e["nit"],e["sector"],e["ciudad"],
              e["direccion"],e["contacto"],e["email"],e["telefono"],
              e["regimen"],e["color"],e.get("icono","📋")))
    conn.commit()

    hoy = __import__('datetime').date(2026, 6, 10)

    total_v = 0
    total_g = 0

    for empresa in EMPRESAS_CLIENTES:
        eid    = empresa["id"]
        clientes   = CLIENTES_POR_EMPRESA[eid]
        proveedores = PROVEEDORES_POR_EMPRESA[eid]

        print(f"\n  [{empresa['id']}] {empresa['razon_social']}")
        print(f"  {'-'*70}")

        # 5-6 facturas de venta
        n_ventas = random.randint(5, 6)
        pool_cli = (clientes * 3)[:n_ventas]
        random.shuffle(pool_cli)
        for i, cliente in enumerate(pool_cli[:n_ventas]):
            numero = f"{empresa['prefijo_venta']}-{empresa['consec_venta'] + i:04d}"
            generar_venta(conn, empresa, cliente, numero, hoy)
            total_v += 1

        # 3-4 facturas de gasto
        n_gastos = random.randint(3, 4)
        pool_prov = (proveedores * 2)[:n_gastos]
        random.shuffle(pool_prov)
        for i, proveedor in enumerate(pool_prov[:n_gastos]):
            numero = f"{empresa['prefijo_gasto']}-{empresa['consec_gasto'] + i:04d}"
            generar_gasto(conn, empresa, proveedor, numero, hoy)
            total_g += 1

    # Resumen
    ventas = conn.execute("SELECT COUNT(*),SUM(total_factura),SUM(valor_neto) FROM facturas_venta").fetchone()
    gastos = conn.execute("SELECT COUNT(*),SUM(total_factura),SUM(valor_neto) FROM facturas_gastos").fetchone()

    print(f"""
=== GENERACION COMPLETADA ===
  Empresas clientes : 6
  Facturas de venta : {ventas[0]} facturas | Total: {ventas[1]/1e6:.1f}M COP | Neto: {ventas[2]/1e6:.1f}M COP
  Facturas de gastos: {gastos[0]} facturas | Total: {gastos[1]/1e6:.1f}M COP | Neto: {gastos[2]/1e6:.1f}M COP
""")
    conn.close()


if __name__ == "__main__":
    main()
