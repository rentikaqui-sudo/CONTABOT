"""
calendario.py — Obligaciones tributarias colombianas 2026.
Fechas exactas del calendario DIAN 2026 (Decreto 2229/2023 + resoluciones 2025).
Fuente: www.dian.gov.co/Calendarios/Calendario_Tributario_2026.pdf
"""

from datetime import date, timedelta
import re

# ── Helpers NIT ───────────────────────────────────────────────────────────────

def _nit_sin_dv(nit: str) -> str:
    """Retorna los dígitos del NIT sin el dígito de verificación."""
    nit = (nit or "").strip()
    if "-" in nit:
        nit = nit.split("-")[0]
    return re.sub(r"[^\d]", "", nit)

def _ultimo_digito(nit: str) -> str:
    """Último dígito significativo del NIT (sin DV)."""
    d = _nit_sin_dv(nit)
    return d[-1] if d else "0"

def _ultimos_dos(nit: str) -> str:
    """Últimos 2 dígitos del NIT (sin DV), como string con cero a la izquierda."""
    d = _nit_sin_dv(nit)
    return d[-2:].zfill(2) if len(d) >= 2 else d.zfill(2)


# ── Retefuente 350 — fechas exactas por período y último dígito ───────────────
# Estructura: mes_periodo → (mes_vto, año_vto, {dígito: día})
# "dígito" = último dígito del NIT sin DV

_RTEFTE = {
    1:  (2,  2026, {"1":10,"2":11,"3":12,"4":13,"5":16,"6":17,"7":18,"8":19,"9":20,"0":23}),
    2:  (3,  2026, {"1":10,"2":11,"3":12,"4":13,"5":16,"6":17,"7":18,"8":19,"9":20,"0":24}),
    3:  (4,  2026, {"1":13,"2":14,"3":15,"4":16,"5":20,"6":21,"7":22,"8":23,"9":24,"0":27}),
    4:  (5,  2026, {"1":12,"2":13,"3":14,"4":15,"5":19,"6":20,"7":21,"8":22,"9":25,"0":26}),
    5:  (6,  2026, {"1":10,"2":11,"3":12,"4":16,"5":17,"6":18,"7":19,"8":22,"9":23,"0":24}),
    6:  (7,  2026, {"1": 9,"2":10,"3":13,"4":14,"5":15,"6":16,"7":17,"8":21,"9":22,"0":23}),
    7:  (8,  2026, {"1":12,"2":13,"3":14,"4":18,"5":19,"6":20,"7":21,"8":24,"9":25,"0":26}),
    8:  (9,  2026, {"1": 9,"2":10,"3":11,"4":14,"5":15,"6":16,"7":17,"8":18,"9":21,"0":22}),
    9:  (10, 2026, {"1": 9,"2":13,"3":14,"4":15,"5":16,"6":19,"7":20,"8":21,"9":22,"0":23}),
    10: (11, 2026, {"1":11,"2":12,"3":13,"4":17,"5":18,"6":19,"7":20,"8":23,"9":24,"0":25}),
    11: (12, 2026, {"1":10,"2":11,"3":14,"4":15,"5":16,"6":17,"7":18,"8":21,"9":22,"0":23}),
    12: (1,  2027, {"1":13,"2":14,"3":15,"4":18,"5":19,"6":20,"7":21,"8":22,"9":25,"0":26}),
}

def _fecha_rtefte(mes_periodo: int, digito: str) -> date:
    mes_vto, año_vto, dias = _RTEFTE[mes_periodo]
    return date(año_vto, mes_vto, dias.get(digito, 15))


# ── Renta — Grandes Contribuyentes (3 cuotas) ────────────────────────────────

_RENTA_GC = {
    "cuota1": {"mes": 2, "año": 2026, "dias": {"1":10,"2":11,"3":12,"4":13,"5":16,"6":17,"7":18,"8":19,"9":20,"0":23}},
    "cuota2": {"mes": 4, "año": 2026, "dias": {"1":13,"2":14,"3":15,"4":16,"5":20,"6":21,"7":22,"8":23,"9":24,"0":27}},
    "cuota3": {"mes": 6, "año": 2026, "dias": {"1":10,"2":11,"3":12,"4":16,"5":17,"6":18,"7":19,"8":22,"9":23,"0":24}},
}

def obligaciones_renta_gc(nit: str, año: int = 2026) -> list:
    d = _ultimo_digito(nit)
    obs = []
    for key, v in _RENTA_GC.items():
        num = key[-1]
        obs.append({
            "tipo":       f"Renta GC — Cuota {num}",
            "periodo":    f"Año {año - 1}",
            "vencimiento": str(date(v["año"], v["mes"], v["dias"].get(d, 15))),
            "frecuencia": "anual",
            "codigo":     "110-GC",
        })
    return obs


# ── Renta — Personas Jurídicas (2 cuotas) ─────────────────────────────────────

_RENTA_JUR = {
    "cuota1": {"mes": 5, "año": 2026, "dias": {"1":12,"2":13,"3":14,"4":15,"5":19,"6":20,"7":21,"8":22,"9":25,"0":26}},
    "cuota2": {"mes": 7, "año": 2026, "dias": {"1": 9,"2":10,"3":13,"4":14,"5":15,"6":16,"7":17,"8":21,"9":22,"0":23}},
}

def obligaciones_renta_juridica(nit: str, año: int = 2026) -> list:
    d = _ultimo_digito(nit)
    obs = []
    for key, v in _RENTA_JUR.items():
        num = key[-1]
        obs.append({
            "tipo":       f"Renta — Cuota {num}",
            "periodo":    f"Año {año - 1}",
            "vencimiento": str(date(v["año"], v["mes"], v["dias"].get(d, 15))),
            "frecuencia": "anual",
            "codigo":     "110",
        })
    return obs


# ── Renta — Personas Naturales (últimos 2 dígitos NIT, ago–oct) ──────────────

_RENTA_NATURAL = [
    ("01","04",  8, 2026, 12),
    ("05","06",  8, 2026, 13),
    ("07","08",  8, 2026, 14),
    ("09","10",  8, 2026, 18),
    ("11","12",  8, 2026, 19),
    ("13","14",  8, 2026, 20),
    ("15","16",  8, 2026, 21),
    ("17","18",  8, 2026, 24),
    ("19","20",  8, 2026, 25),
    ("21","22",  8, 2026, 26),
    ("23","24",  8, 2026, 27),
    ("25","26",  8, 2026, 28),
    ("27","28",  9, 2026,  1),
    ("29","30",  9, 2026,  2),
    ("31","32",  9, 2026,  3),
    ("33","34",  9, 2026,  4),
    ("35","36",  9, 2026,  7),
    ("37","38",  9, 2026,  8),
    ("39","40",  9, 2026,  9),
    ("41","42",  9, 2026, 10),
    ("43","44",  9, 2026, 11),
    ("45","46",  9, 2026, 14),
    ("47","48",  9, 2026, 15),
    ("49","50",  9, 2026, 16),
    ("51","52",  9, 2026, 17),
    ("53","54",  9, 2026, 18),
    ("55","56",  9, 2026, 21),
    ("57","58",  9, 2026, 22),
    ("59","60",  9, 2026, 23),
    ("61","62",  9, 2026, 24),
    ("63","64",  9, 2026, 25),
    ("65","66",  9, 2026, 28),
    ("67","68", 10, 2026,  1),
    ("69","70", 10, 2026,  2),
    ("71","72", 10, 2026,  5),
    ("73","74", 10, 2026,  6),
    ("75","76", 10, 2026,  7),
    ("77","78", 10, 2026,  8),
    ("79","80", 10, 2026,  9),
    ("81","82", 10, 2026, 13),
    ("83","84", 10, 2026, 14),
    ("85","86", 10, 2026, 15),
    ("87","88", 10, 2026, 16),
    ("89","90", 10, 2026, 19),
    ("91","92", 10, 2026, 20),
    ("93","94", 10, 2026, 21),
    ("95","96", 10, 2026, 22),
    ("97","98", 10, 2026, 23),
    ("99","00", 10, 2026, 26),
]

def obligaciones_renta_natural(nit: str, año: int = 2026) -> list:
    ult2 = _ultimos_dos(nit)
    num = int(ult2)
    for desde, hasta, mes, anio, dia in _RENTA_NATURAL:
        d_ini = int(desde)
        d_fin = int(hasta) if hasta != "00" else 100
        if hasta == "00":
            if num == 99 or num == 0:
                return [{
                    "tipo":       "Renta",
                    "periodo":    f"Año {año - 1}",
                    "vencimiento": str(date(anio, mes, dia)),
                    "frecuencia": "anual",
                    "codigo":     "210",
                    "nota":       f"NIT ...{ult2} → {dia} {'ago' if mes==8 else 'sep' if mes==9 else 'oct'} {anio}",
                }]
        if d_ini <= num <= int(hasta):
            return [{
                "tipo":       "Renta",
                "periodo":    f"Año {año - 1}",
                "vencimiento": str(date(anio, mes, dia)),
                "frecuencia": "anual",
                "codigo":     "210",
                "nota":       f"NIT ...{ult2} → {dia} {'ago' if mes==8 else 'sep' if mes==9 else 'oct'} {anio}",
            }]
    # Fallback: último día
    return [{"tipo":"Renta","periodo":f"Año {año-1}","vencimiento":str(date(año,10,26)),"frecuencia":"anual","codigo":"210"}]


# ── Retefuente 350 — mensual ──────────────────────────────────────────────────

def obligaciones_retefte(nit: str, año: int = 2026) -> list:
    d = _ultimo_digito(nit)
    obs = []
    for mes in range(1, 13):
        mes_vto, año_vto, dias = _RTEFTE[mes]
        obs.append({
            "tipo":       "Retefuente 350",
            "periodo":    f"{_nombre_mes(mes)} {año}",
            "vencimiento": str(date(año_vto, mes_vto, dias.get(d, 15))),
            "frecuencia": "mensual",
            "codigo":     "350",
        })
    return obs


# ── IVA — Bimestral (Grandes Contribuyentes) ─────────────────────────────────
# Mismos días que Retefuente del mes de vencimiento

_IVA_BIMESTRAL_PERIODOS = [
    (1, "Ene–Feb", 2),   # vence Mar → igual a Rtefte período Feb
    (2, "Mar–Abr", 4),   # vence May → igual a Rtefte período Abr
    (3, "May–Jun", 6),   # vence Jul → igual a Rtefte período Jun
    (4, "Jul–Ago", 8),   # vence Sep → igual a Rtefte período Ago
    (5, "Sep–Oct", 10),  # vence Nov → igual a Rtefte período Oct
    (6, "Nov–Dic", 12),  # vence Ene 2027 → igual a Rtefte período Dic
]

def obligaciones_iva_bimestral(nit: str, año: int = 2026) -> list:
    d = _ultimo_digito(nit)
    obs = []
    for num, label, mes_rtefte in _IVA_BIMESTRAL_PERIODOS:
        mes_vto, año_vto, dias = _RTEFTE[mes_rtefte]
        obs.append({
            "tipo":       "IVA Bimestral F-300",
            "periodo":    f"{label} {año}",
            "vencimiento": str(date(año_vto, mes_vto, dias.get(d, 15))),
            "frecuencia": "bimestral",
            "codigo":     "300B",
        })
    return obs


# ── IVA — Cuatrimestral (Demás responsables) ─────────────────────────────────

_IVA_CUATRIMESTRAL_PERIODOS = [
    (1, "Ene–Abr", 4),   # vence May → igual a Rtefte período Abr
    (2, "May–Ago", 8),   # vence Sep → igual a Rtefte período Ago
    (3, "Sep–Dic", 12),  # vence Ene 2027 → igual a Rtefte período Dic
]

def obligaciones_iva_cuatrimestral(nit: str, año: int = 2026) -> list:
    d = _ultimo_digito(nit)
    obs = []
    for num, label, mes_rtefte in _IVA_CUATRIMESTRAL_PERIODOS:
        mes_vto, año_vto, dias = _RTEFTE[mes_rtefte]
        obs.append({
            "tipo":       "IVA Cuatrimestral F-300",
            "periodo":    f"{label} {año}",
            "vencimiento": str(date(año_vto, mes_vto, dias.get(d, 15))),
            "frecuencia": "cuatrimestral",
            "codigo":     "300C",
        })
    return obs


# ── ICA — Bimestral (mismo calendario que IVA bimestral) ─────────────────────

def obligaciones_ica(nit: str, año: int = 2026) -> list:
    d = _ultimo_digito(nit)
    labels = ["Ene–Feb","Mar–Abr","May–Jun","Jul–Ago","Sep–Oct","Nov–Dic"]
    obs = []
    for i, (num, label, mes_rtefte) in enumerate(_IVA_BIMESTRAL_PERIODOS):
        mes_vto, año_vto, dias = _RTEFTE[mes_rtefte]
        obs.append({
            "tipo":       "ICA",
            "periodo":    f"{label} {año}",
            "vencimiento": str(date(año_vto, mes_vto, dias.get(d, 15))),
            "frecuencia": "bimestral",
            "codigo":     "ICA",
        })
    return obs


# ── Todas las obligaciones según régimen ──────────────────────────────────────

_REGIMEN_OBLIGACIONES = {
    # régimen → lista de funciones que aplican
    "GranContribuyente": ["renta_gc",  "iva_bimestral", "rtefte", "ica"],
    "Juridica":          ["renta_jur", "iva_cuatrimestral", "rtefte", "ica"],
    "Natural":           ["renta_natural"],
    "Simple":            ["renta_natural", "ica"],
    "Simplificado":      ["renta_natural"],
}

def todas_las_obligaciones(nit: str, año: int = 2026, regimen: str = "Juridica") -> list:
    regimen = regimen or "Juridica"
    aplica  = _REGIMEN_OBLIGACIONES.get(regimen, _REGIMEN_OBLIGACIONES["Juridica"])
    obs = []
    if "renta_gc"         in aplica: obs += obligaciones_renta_gc(nit, año)
    if "renta_jur"        in aplica: obs += obligaciones_renta_juridica(nit, año)
    if "renta_natural"    in aplica: obs += obligaciones_renta_natural(nit, año)
    if "iva_bimestral"    in aplica: obs += obligaciones_iva_bimestral(nit, año)
    if "iva_cuatrimestral"in aplica: obs += obligaciones_iva_cuatrimestral(nit, año)
    if "rtefte"           in aplica: obs += obligaciones_retefte(nit, año)
    if "ica"              in aplica: obs += obligaciones_ica(nit, año)
    obs.sort(key=lambda o: o["vencimiento"])
    return obs


# ── Obligaciones próximas (para Telegram) ────────────────────────────────────

def obligaciones_proximas(empresas: list, dias: int = 7, año: int = 2026) -> list:
    hoy    = date.today()
    limite = hoy + timedelta(days=dias)
    prox   = []
    for e in empresas:
        nit     = e.get("nit", "")
        regimen = e.get("regimen") or "Juridica"
        for ob in todas_las_obligaciones(nit, año, regimen):
            vto = date.fromisoformat(ob["vencimiento"])
            if hoy <= vto <= limite:
                prox.append({
                    "empresa_id":    e.get("id"),
                    "empresa":       e.get("razon_social", ""),
                    "nit":           nit,
                    "obligacion":    ob,
                    "dias_restantes": (vto - hoy).days,
                })
    prox.sort(key=lambda x: x["obligacion"]["vencimiento"])
    return prox


# ── Helper ────────────────────────────────────────────────────────────────────

def _nombre_mes(m: int) -> str:
    return ["Ene","Feb","Mar","Abr","May","Jun",
            "Jul","Ago","Sep","Oct","Nov","Dic"][m - 1]
