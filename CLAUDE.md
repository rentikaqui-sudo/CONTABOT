# ContaBot Demo — Instrucciones del Proyecto

## Qué es esto
Demo de automatización contable colombiana para mostrarle a un contador cómo la automatización puede ahorrarle tiempo. Empresa ficticia: **Distribuidora ABC S.A.S.** (NIT 900.456.789-3).

## Stack
- **Python 3.12** + Flask (backend y generación de PDFs)
- **ReportLab** — generación de facturas PDF con formato DIAN
- **PyMuPDF** — extracción de datos de PDFs
- **SQLite** (`data/demo.db`) — base de datos local, sin servidor
- **HTML + Chart.js** — dashboard frontend
- **Windows 11** — todo corre localmente, sin servicios externos

## Estructura
```
contador/
├── CLAUDE.md
├── requirements.txt
├── start_demo.bat              ← Doble clic para iniciar todo
├── data/
│   ├── demo.db                 ← SQLite con todas las tablas
│   ├── facturas_venta/         ← 28 PDFs de facturas emitidas
│   └── facturas_gastos/        ← 22 PDFs de facturas recibidas
├── scripts/
│   ├── datos_colombia.py       ← Datos maestros (clientes, proveedores, tasas)
│   ├── generate_pdfs.py        ← Genera los 50 PDFs y puebla demo.db
│   ├── procesar_facturas.py    ← Extrae datos de PDFs con PyMuPDF
│   └── conciliacion.py         ← Lógica de conciliación bancaria
├── api/
│   └── server.py               ← Flask API (puerto 5000)
└── ui/
    ├── index.html              ← Dashboard principal
    ├── demo.js
    └── styles.css
```

## Cómo correr
```bash
pip install -r requirements.txt
python scripts/generate_pdfs.py   # genera los 50 PDFs
python api/server.py               # inicia el servidor
# Abrir http://localhost:5000
```

## Sistema colombiano implementado
- **NIT** (no CUIT): formato 900.456.789-3
- **CUFE**: hash SHA-384 de 96 chars (Código Único de Factura Electrónica DIAN)
- **Resolución DIAN**: número habilitante en cada factura
- **IVA 19%** (general), 5% y 0% según producto
- **Retefuente**: 2.5% compras, 4% servicios, 11% honorarios
- **ReteIVA**: 15% del IVA (solo grandes contribuyentes)
- **ReteICA**: 4.14‰ (Bogotá)
- Bancos: Bancolombia, Davivienda, Banco de Bogotá, BBVA Colombia

## Datos ficticios
- 15 clientes colombianos con NITs y ciudades reales
- 15 proveedores por categoría (insumos, transporte, honorarios, etc.)
- 28 facturas de venta + 22 facturas de gastos = 50 total
- Período: abril–junio 2026

## Memoria de sesión
**REGLA IMPORTANTE**: Solo guardar memoria cuando el usuario diga explícitamente
"guarda esto", "recuerda esto", o "memoria: [contenido]".
No guardar automáticamente nada de esta sesión sin autorización explícita.
Para invocar memoria guardada, el usuario debe decir "recuerda" o "carga memoria".

## Flujos de la demo (orden de presentación)
1. **Flujo A** — Procesamiento de facturas PDF (el "wow")
2. **Flujo B** — Conciliación bancaria automática
3. **Flujo C** — Dashboard financiero en tiempo real
4. **Flujo D** — Alertas de vencimientos + emails automáticos

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
