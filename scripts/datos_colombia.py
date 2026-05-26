"""
Datos ficticios colombianos — Estudio Contable Aristizábal & Asociados
El contador maneja 6 empresas clientes de distintos sectores.
"""

import random
from datetime import date, timedelta
import hashlib, uuid

# ─── El estudio contable (el contador) ───────────────────────────────────────

ESTUDIO = {
    "nombre":    "Estudio Contable Aristizábal & Asociados",
    "nit":       "19.845.234-1",
    "contador":  "Federico Aristizábal Gómez",
    "registro":  "T.P. 124567-T",
    "ciudad":    "Bogotá D.C.",
    "email":     "info@contablearistizabal.com.co",
    "telefono":  "3158904321",
}

# ─── 6 Empresas clientes del contador ────────────────────────────────────────

EMPRESAS_CLIENTES = [
    {
        "id": 1,
        "razon_social": "Restaurante El Fogón Paisa S.A.S.",
        "nit": "901.234.567-1",
        "sector": "Alimentos y Bebidas",
        "ciiu": "5611",
        "ciudad": "Bogotá D.C.",
        "direccion": "Cra 13 #85-32, Chapinero",
        "contacto": "Margarita Ospina",
        "email": "admin@elfogonpaisa.com.co",
        "telefono": "3102345678",
        "regimen": "Responsable de IVA",
        "color": "#10b981",
        "icono": "🍽️",
        "prefijo_venta": "FV",
        "prefijo_gasto": "FC",
        "consec_venta": 2100,
        "consec_gasto": 8100,
        "resolucion_dian": "18764000002101",
    },
    {
        "id": 2,
        "razon_social": "Consultora Digital Pro S.A.S.",
        "nit": "900.876.543-2",
        "sector": "Tecnología y Consultoría",
        "ciiu": "6201",
        "ciudad": "Bogotá D.C.",
        "direccion": "Av. El Dorado #69-76, Of. 503",
        "contacto": "Sebastián Vargas",
        "email": "contabilidad@digitalpro.co",
        "telefono": "3013456789",
        "regimen": "Responsable de IVA",
        "color": "#3b82f6",
        "icono": "💻",
        "prefijo_venta": "FV",
        "prefijo_gasto": "FC",
        "consec_venta": 3200,
        "consec_gasto": 9200,
        "resolucion_dian": "18764000003201",
    },
    {
        "id": 3,
        "razon_social": "Ferretería y Materiales Los Andes Ltda.",
        "nit": "830.456.789-3",
        "sector": "Comercio al por Menor",
        "ciiu": "4752",
        "ciudad": "Medellín",
        "direccion": "Calle 30 #44-21, Guayabal",
        "contacto": "Hernando Restrepo",
        "email": "herrestrepo@ferreteriandes.com",
        "telefono": "3044567890",
        "regimen": "Responsable de IVA",
        "color": "#f59e0b",
        "icono": "🔧",
        "prefijo_venta": "FV",
        "prefijo_gasto": "FC",
        "consec_venta": 4300,
        "consec_gasto": 4300,
        "resolucion_dian": "18764000004301",
    },
    {
        "id": 4,
        "razon_social": "Transportes Rápidos del Norte S.A.",
        "nit": "890.567.890-4",
        "sector": "Transporte y Logística",
        "ciiu": "4923",
        "ciudad": "Barranquilla",
        "direccion": "Cra 46 #74-50, Barranquilla",
        "contacto": "Claudia Herrera",
        "email": "claudia.herrera@transrapido.co",
        "telefono": "3055678901",
        "regimen": "Responsable de IVA",
        "color": "#a855f7",
        "icono": "🚛",
        "prefijo_venta": "FV",
        "prefijo_gasto": "FC",
        "consec_venta": 5400,
        "consec_gasto": 5400,
        "resolucion_dian": "18764000005401",
    },
    {
        "id": 5,
        "razon_social": "Clínica Dental Sonrisa Perfecta Ltda.",
        "nit": "805.678.901-5",
        "sector": "Salud",
        "ciiu": "8621",
        "ciudad": "Cali",
        "direccion": "Av. 6N #25-32, Cali",
        "contacto": "Dra. Andrea Moncayo",
        "email": "admin@sonrisaperfecta.com.co",
        "telefono": "3166789012",
        "regimen": "Responsable de IVA",
        "color": "#06b6d4",
        "icono": "🦷",
        "prefijo_venta": "FV",
        "prefijo_gasto": "FC",
        "consec_venta": 6500,
        "consec_gasto": 6500,
        "resolucion_dian": "18764000006501",
    },
    {
        "id": 6,
        "razon_social": "Constructora Arenas & Cía S.A.S.",
        "nit": "900.789.012-6",
        "sector": "Construcción",
        "ciiu": "4111",
        "ciudad": "Bogotá D.C.",
        "direccion": "Calle 100 #19-61, Of. 201",
        "contacto": "Jorge Arenas",
        "email": "jorge.arenas@constructoraarenas.co",
        "telefono": "3007890123",
        "regimen": "Gran Contribuyente",
        "color": "#ef4444",
        "icono": "🏗️",
        "prefijo_venta": "FV",
        "prefijo_gasto": "FC",
        "consec_venta": 7600,
        "consec_gasto": 7600,
        "resolucion_dian": "18764000007601",
    },
]

# ─── Tasas colombianas ────────────────────────────────────────────────────────

TASAS = {
    "iva_general":            0.19,
    "iva_reducido":           0.05,
    "iva_cero":               0.00,
    "retefuente_servicios":   0.04,
    "retefuente_compras":     0.025,
    "retefuente_honorarios":  0.11,
    "retefuente_transporte":  0.04,
    "retefuente_arrendamiento":0.035,
    "reteiva":                0.15,
    "reteica_bogota":         0.00414,
    "reteica_medellin":       0.00414,
    "reteica_barranquilla":   0.00414,
    "reteica_cali":           0.00414,
}

# ─── Clientes de cada empresa (a quiénes les venden) ─────────────────────────

CLIENTES_POR_EMPRESA = {
    # Restaurante El Fogón Paisa
    1: [
        {"razon_social": "Eventos Corporativos Andinos S.A.S.", "nit": "900.111.001-1", "ciudad": "Bogotá", "email": "eventos@andinos.co", "telefono": "3100010001", "gran_contribuyente": False},
        {"razon_social": "Catering y Banquetes Premium Ltda.", "nit": "830.111.002-2", "ciudad": "Bogotá", "email": "info@cateringpremium.co", "telefono": "3010010002", "gran_contribuyente": False},
        {"razon_social": "Universidad Central S.A.", "nit": "860.007.384-1", "ciudad": "Bogotá", "email": "proveedores@ucentral.edu.co", "telefono": "6013238600", "gran_contribuyente": True},
        {"razon_social": "Caja de Compensación Cafam", "nit": "860.007.760-3", "ciudad": "Bogotá", "email": "compras@cafam.com.co", "telefono": "6013257400", "gran_contribuyente": True},
    ],
    # Consultora Digital Pro
    2: [
        {"razon_social": "Banco Caja Social S.A.", "nit": "860.007.335-4", "ciudad": "Bogotá", "email": "proveedores@bancocajasocial.com", "telefono": "6013079000", "gran_contribuyente": True},
        {"razon_social": "Aseguradora Colmena S.A.", "nit": "860.007.649-7", "ciudad": "Bogotá", "email": "tech@colmena.com.co", "telefono": "6017443700", "gran_contribuyente": True},
        {"razon_social": "Clínica Palermo S.A.", "nit": "860.007.760-3", "ciudad": "Bogotá", "email": "sistemas@clinicapalermo.com", "telefono": "6018280040", "gran_contribuyente": False},
        {"razon_social": "Grupo Energía Bogotá S.A. E.S.P.", "nit": "800.116.738-7", "ciudad": "Bogotá", "email": "contratos@grupoenergabogota.com", "telefono": "6073410000", "gran_contribuyente": True},
    ],
    # Ferretería Los Andes
    3: [
        {"razon_social": "Constructora Pizano S.A.", "nit": "890.900.524-4", "ciudad": "Medellín", "email": "compras@pizano.com.co", "telefono": "6044440000", "gran_contribuyente": False},
        {"razon_social": "Cemex Colombia S.A.", "nit": "860.002.544-8", "ciudad": "Bogotá", "email": "pedidos@cemex.co", "telefono": "6014234000", "gran_contribuyente": True},
        {"razon_social": "Maestro Home Center S.A.S.", "nit": "900.465.809-1", "ciudad": "Medellín", "email": "proveedores@maestro.com.co", "telefono": "6044910000", "gran_contribuyente": False},
        {"razon_social": "Arquitectura y Diseño Urbano Ltda.", "nit": "811.022.334-5", "ciudad": "Medellín", "email": "compras@arqdiseño.co", "telefono": "3046660001", "gran_contribuyente": False},
    ],
    # Transportes Rápidos del Norte
    4: [
        {"razon_social": "Postobón S.A.", "nit": "860.001.022-7", "ciudad": "Bogotá", "email": "logistica@postobon.com", "telefono": "6018862000", "gran_contribuyente": True},
        {"razon_social": "Colombina S.A.", "nit": "890.300.473-2", "ciudad": "Cali", "email": "transporte@colombina.com", "telefono": "6028868686", "gran_contribuyente": True},
        {"razon_social": "Almacenes Éxito S.A.", "nit": "860.029.966-1", "ciudad": "Medellín", "email": "proveedores@exito.com.co", "telefono": "6044444444", "gran_contribuyente": True},
        {"razon_social": "Bavaria S.A.", "nit": "860.034.313-4", "ciudad": "Bogotá", "email": "logistica@bavaria.co", "telefono": "6016029000", "gran_contribuyente": True},
    ],
    # Clínica Dental Sonrisa
    5: [
        {"razon_social": "EPS Sura S.A.", "nit": "800.088.702-3", "ciudad": "Medellín", "email": "proveedores@sura.com.co", "telefono": "6044447777", "gran_contribuyente": True},
        {"razon_social": "Nueva EPS S.A.", "nit": "900.156.264-0", "ciudad": "Bogotá", "email": "prestadores@nuevaeps.com.co", "telefono": "6018000700", "gran_contribuyente": False},
        {"razon_social": "Salud Total EPS-S S.A.", "nit": "830.113.831-6", "ciudad": "Bogotá", "email": "cuentas@saludtotal.com.co", "telefono": "6018804748", "gran_contribuyente": False},
        {"razon_social": "Compensar EPS", "nit": "860.066.942-3", "ciudad": "Bogotá", "email": "facturacion@compensar.com", "telefono": "6017456789", "gran_contribuyente": True},
    ],
    # Constructora Arenas
    6: [
        {"razon_social": "Fondo Nacional del Ahorro", "nit": "899.999.023-1", "ciudad": "Bogotá", "email": "contratos@fna.gov.co", "telefono": "6018002222", "gran_contribuyente": True},
        {"razon_social": "Fiduciaria Bogotá S.A.", "nit": "860.034.313-4", "ciudad": "Bogotá", "email": "proyectos@fiduciariabogota.com", "telefono": "6014222222", "gran_contribuyente": True},
        {"razon_social": "Inversiones Urbanas Capital S.A.S.", "nit": "900.523.451-7", "ciudad": "Bogotá", "email": "contratos@invcapital.co", "telefono": "3001230001", "gran_contribuyente": False},
        {"razon_social": "Alcaldía de Bogotá — Secretaría de Hábitat", "nit": "899.999.061-9", "ciudad": "Bogotá", "email": "contratacion@habitat.gov.co", "telefono": "6013837777", "gran_contribuyente": True},
    ],
}

# ─── Proveedores de cada empresa (a quiénes les compran) ─────────────────────

PROVEEDORES_POR_EMPRESA = {
    # Restaurante El Fogón
    1: [
        {"razon_social": "Proveedor Carnes La Sabana S.A.S.", "nit": "900.200.001-1", "ciudad": "Bogotá", "email": "ventas@carneslasabana.co", "telefono": "3100200001", "categoria": "insumos"},
        {"razon_social": "Abastos Fruver del Campo Ltda.", "nit": "830.200.002-2", "ciudad": "Bogotá", "email": "pedidos@fruver.com.co", "telefono": "3010200002", "categoria": "insumos"},
        {"razon_social": "Gas Natural Fenosa Colombia S.A.", "nit": "830.050.555-5", "ciudad": "Bogotá", "email": "empresas@gasnatural.com.co", "telefono": "6017005055", "categoria": "servicios_publicos"},
        {"razon_social": "Arrendamientos Chapinero S.A.S.", "nit": "900.200.004-4", "ciudad": "Bogotá", "email": "contratos@chapineroarr.co", "telefono": "3120200004", "categoria": "arrendamiento"},
    ],
    # Consultora Digital Pro
    2: [
        {"razon_social": "Amazon Web Services Colombia", "nit": "900.500.001-1", "ciudad": "Bogotá", "email": "billing@aws.amazon.com", "telefono": "3000500001", "categoria": "tecnologia"},
        {"razon_social": "Telecomunicaciones ETB S.A.", "nit": "860.002.534-1", "ciudad": "Bogotá", "email": "empresas@etb.com.co", "telefono": "6017340000", "categoria": "telecomunicaciones"},
        {"razon_social": "Asesorías Jurídicas Legales Colombia Ltda.", "nit": "830.999.000-9", "ciudad": "Bogotá", "email": "facturacion@legalcolombia.co", "telefono": "3130009999", "categoria": "honorarios"},
        {"razon_social": "Arrendamientos Oficinas El Dorado S.A.S.", "nit": "900.500.004-4", "ciudad": "Bogotá", "email": "admin@eldoradoofi.co", "telefono": "3100500004", "categoria": "arrendamiento"},
    ],
    # Ferretería Los Andes
    3: [
        {"razon_social": "Acerías de Colombia S.A. Acesco", "nit": "890.101.524-3", "ciudad": "Medellín", "email": "ventas@acesco.com.co", "telefono": "6044609090", "categoria": "insumos"},
        {"razon_social": "Corona Industrial S.A.S.", "nit": "890.900.495-7", "ciudad": "Medellín", "email": "distribuidores@corona.com.co", "telefono": "6044480000", "categoria": "insumos"},
        {"razon_social": "Transportes y Logística Andina Ltda.", "nit": "830.222.333-2", "ciudad": "Bogotá", "email": "ops@transandina.co", "telefono": "3010002222", "categoria": "transporte"},
        {"razon_social": "Vigilancia y Seguridad Privada Atlas S.A.", "nit": "860.040.444-4", "ciudad": "Bogotá", "email": "contratos@atlasseguridad.com", "telefono": "6017004044", "categoria": "seguridad"},
    ],
    # Transportes Rápidos del Norte
    4: [
        {"razon_social": "Terpel S.A.", "nit": "830.002.528-3", "ciudad": "Bogotá", "email": "corporativo@terpel.com", "telefono": "6013382828", "categoria": "insumos"},
        {"razon_social": "Seguros del Estado S.A.", "nit": "860.006.793-8", "ciudad": "Bogotá", "email": "corporativo@segurosestado.com", "telefono": "6013077000", "categoria": "seguros"},
        {"razon_social": "Taller Automotriz Barranquilla S.A.S.", "nit": "900.600.003-3", "ciudad": "Barranquilla", "email": "facturacion@tallerba.co", "telefono": "3050600003", "categoria": "servicios"},
        {"razon_social": "Peajes y Concesiones Colombia S.A.", "nit": "900.600.004-4", "ciudad": "Bogotá", "email": "facturacion@peajescol.co", "telefono": "3100600004", "categoria": "servicios"},
    ],
    # Clínica Dental Sonrisa
    5: [
        {"razon_social": "Colgate-Palmolive Colombia Ltda.", "nit": "860.002.153-4", "ciudad": "Bogotá", "email": "distribuidores@colgate.com.co", "telefono": "6016011111", "categoria": "insumos"},
        {"razon_social": "Instrumental Odontológico S.A.S.", "nit": "900.700.002-2", "ciudad": "Cali", "email": "ventas@instrodont.co", "telefono": "3160700002", "categoria": "insumos"},
        {"razon_social": "Energía del Pacífico S.A. E.S.P.", "nit": "805.000.437-3", "ciudad": "Cali", "email": "empresas@epsa.com.co", "telefono": "6028981000", "categoria": "servicios_publicos"},
        {"razon_social": "Publicidad y Marketing Digital Pro S.A.S.", "nit": "900.888.999-8", "ciudad": "Bogotá", "email": "cuentas@marketingpro.com.co", "telefono": "3020008888", "categoria": "publicidad"},
    ],
    # Constructora Arenas
    6: [
        {"razon_social": "Cementos Argos S.A.", "nit": "860.035.827-3", "ciudad": "Medellín", "email": "distribuidores@argos.com.co", "telefono": "6044441000", "categoria": "insumos"},
        {"razon_social": "Ferrasa S.A.S.", "nit": "890.301.473-2", "ciudad": "Cali", "email": "ventas@ferrasa.com.co", "telefono": "6028864444", "categoria": "insumos"},
        {"razon_social": "Maquinaria y Equipos Bogotá S.A.S.", "nit": "900.800.003-3", "ciudad": "Bogotá", "email": "arrendamiento@maqequipos.co", "telefono": "3100800003", "categoria": "arrendamiento"},
        {"razon_social": "Arquitectos e Ingenieros Asociados Ltda.", "nit": "830.800.004-4", "ciudad": "Bogotá", "email": "honorarios@aialda.co", "telefono": "3010800004", "categoria": "honorarios"},
    ],
}

# ─── Productos de venta por sector ───────────────────────────────────────────

PRODUCTOS_POR_EMPRESA = {
    1: [  # Restaurante
        {"descripcion": "Servicio de catering eventos corporativos", "precio_base": 1800000, "iva": 0.19, "unidad": "Evento"},
        {"descripcion": "Almuerzo ejecutivo empresarial (por persona)", "precio_base": 32000, "iva": 0.19, "unidad": "Persona"},
        {"descripcion": "Paquete desayuno de trabajo (por persona)", "precio_base": 22000, "iva": 0.19, "unidad": "Persona"},
        {"descripcion": "Servicio de restaurante — factura mensual", "precio_base": 4500000, "iva": 0.19, "unidad": "Mes"},
        {"descripcion": "Refrigerios reunión directivos (por persona)", "precio_base": 18000, "iva": 0.19, "unidad": "Persona"},
    ],
    2: [  # Consultoría Digital
        {"descripcion": "Desarrollo de aplicación web a medida", "precio_base": 12000000, "iva": 0.19, "unidad": "Proyecto"},
        {"descripcion": "Consultoría en transformación digital", "precio_base": 6500000, "iva": 0.19, "unidad": "Mes"},
        {"descripcion": "Soporte técnico mensual — SLA 24/7", "precio_base": 3200000, "iva": 0.19, "unidad": "Mes"},
        {"descripcion": "Licencia software ERP empresarial", "precio_base": 8900000, "iva": 0.19, "unidad": "Año"},
        {"descripcion": "Capacitación tecnológica (por sesión)", "precio_base": 1500000, "iva": 0.19, "unidad": "Sesión"},
    ],
    3: [  # Ferretería
        {"descripcion": "Varilla corrugada 1/2\" x 6m (por unidad)", "precio_base": 28500, "iva": 0.19, "unidad": "Unidad"},
        {"descripcion": "Cemento Argos 50kg (por bulto)", "precio_base": 31000, "iva": 0.19, "unidad": "Bulto"},
        {"descripcion": "Tubería PVC 4\" x 6m", "precio_base": 45000, "iva": 0.19, "unidad": "Unidad"},
        {"descripcion": "Pintura vinilo interior 5 galones", "precio_base": 125000, "iva": 0.19, "unidad": "Galón"},
        {"descripcion": "Cable eléctrico calibre 12 (rollo 100m)", "precio_base": 185000, "iva": 0.19, "unidad": "Rollo"},
    ],
    4: [  # Transporte
        {"descripcion": "Flete terrestre Bogotá-Barranquilla (por tonelada)", "precio_base": 380000, "iva": 0.19, "unidad": "Tonelada"},
        {"descripcion": "Servicio de transporte mensual — contrato", "precio_base": 8500000, "iva": 0.19, "unidad": "Mes"},
        {"descripcion": "Flete especial carga refrigerada", "precio_base": 620000, "iva": 0.19, "unidad": "Viaje"},
        {"descripcion": "Distribución urbana Barranquilla (por despacho)", "precio_base": 95000, "iva": 0.19, "unidad": "Despacho"},
    ],
    5: [  # Clínica Dental
        {"descripcion": "Servicio odontológico integral — EPS", "precio_base": 285000, "iva": 0.0, "unidad": "Paciente"},
        {"descripcion": "Ortodoncia metálica completa", "precio_base": 3200000, "iva": 0.0, "unidad": "Tratamiento"},
        {"descripcion": "Consulta especializada endodoncia", "precio_base": 350000, "iva": 0.0, "unidad": "Consulta"},
        {"descripcion": "Blanqueamiento dental profesional", "precio_base": 450000, "iva": 0.0, "unidad": "Sesión"},
        {"descripcion": "Facturación mensual EPS — capitación", "precio_base": 12000000, "iva": 0.0, "unidad": "Mes"},
    ],
    6: [  # Constructora
        {"descripcion": "Construcción vivienda VIS — avance de obra", "precio_base": 45000000, "iva": 0.0, "unidad": "Acta"},
        {"descripcion": "Urbanización y obras de infraestructura", "precio_base": 28000000, "iva": 0.0, "unidad": "Etapa"},
        {"descripcion": "Interventoría técnica de obra", "precio_base": 8500000, "iva": 0.19, "unidad": "Mes"},
        {"descripcion": "Estudio de suelos y diseño estructural", "precio_base": 12000000, "iva": 0.19, "unidad": "Proyecto"},
    ],
}

# ─── Retenciones por categoría de gasto ──────────────────────────────────────

RETENCIONES_GASTO = {
    "insumos":          {"retefuente": 0.025, "reteiva": 0.0,  "reteica": 0.00414, "iva": 0.19},
    "transporte":       {"retefuente": 0.04,  "reteiva": 0.0,  "reteica": 0.00414, "iva": 0.19},
    "servicios":        {"retefuente": 0.04,  "reteiva": 0.15, "reteica": 0.00414, "iva": 0.19},
    "telecomunicaciones":{"retefuente":0.025, "reteiva": 0.0,  "reteica": 0.00414, "iva": 0.19},
    "seguros":          {"retefuente": 0.025, "reteiva": 0.0,  "reteica": 0.0,     "iva": 0.0},
    "arrendamiento":    {"retefuente": 0.035, "reteiva": 0.0,  "reteica": 0.00414, "iva": 0.19},
    "publicidad":       {"retefuente": 0.04,  "reteiva": 0.15, "reteica": 0.00414, "iva": 0.19},
    "honorarios":       {"retefuente": 0.11,  "reteiva": 0.15, "reteica": 0.00414, "iva": 0.19},
    "tecnologia":       {"retefuente": 0.04,  "reteiva": 0.15, "reteica": 0.00414, "iva": 0.19},
    "seguridad":        {"retefuente": 0.04,  "reteiva": 0.0,  "reteica": 0.00414, "iva": 0.19},
    "servicios_publicos":{"retefuente":0.025, "reteiva": 0.0,  "reteica": 0.0,     "iva": 0.19},
}

# ─── Utilidades ──────────────────────────────────────────────────────────────

def fecha_aleatoria():
    inicio = date(2026, 3, 1)
    dias = random.randint(0, 110)
    return inicio + timedelta(days=dias)

def generar_cufe():
    return hashlib.sha384(str(uuid.uuid4()).encode()).hexdigest()[:96]

def formatear_pesos(valor):
    return f"${int(valor):,}".replace(",", ".")
