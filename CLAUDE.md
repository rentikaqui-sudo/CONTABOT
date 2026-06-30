# ContaBot — Instrucciones del Proyecto

## Qué es esto
Sistema de automatización contable colombiana en producción. Un contador (Federico Aristizábal) gestiona múltiples empresas clientes. ContaBot extrae facturas electrónicas DIAN automáticamente desde Gmail, las registra en Supabase, y genera pre-liquidaciones de impuestos.

## Stack
- **Python 3.12** + Flask — backend API (puerto 5000), desplegado en Railway
- **Supabase** (PostgreSQL) — base de datos principal, autenticación multi-contador
- **PyMuPDF + lxml** — extracción de datos de PDFs y XMLs DIAN
- **Gmail OAuth2** — escaneo automático de facturas por correo
- **openpyxl** — generación de Excel contable (6 hojas)
- **HTML + Chart.js + Vanilla JS** — dashboard frontend
- **Telegram Bot** — notificaciones al contador
- **Railway** — hosting producción (`contabot-demo-production.up.railway.app`)
- **GitHub** — repo privado `rentikaqui-sudo/CONTABOT`, branch `main`

## Estructura
```
contador/
├── CLAUDE.md
├── requirements.txt
├── manual_contabot.html        ← Manual de usuario
├── api/
│   └── server.py               ← Flask API completa (~2800 líneas)
├── scripts/
│   ├── extractor.py            ← Extracción XML/PDF DIAN, guardar pendientes
│   ├── gmail_facturas.py       ← Escaneo Gmail, procesamiento de mensajes
│   └── calendario.py           ← Obligaciones tributarias colombianas
├── ui/
│   ├── index.html              ← App principal (SPA)
│   ├── demo.js                 ← Lógica frontend (~1400 líneas)
│   └── styles.css
└── data/
    └── demo.db                 ← SQLite local (solo dev, ignorado en git)
```

## Cómo correr localmente
```bash
pip install -r requirements.txt
python api/server.py   # inicia en http://localhost:5000
```

## Sistema tributario colombiano implementado
- **NIT**: formato 900.456.789-3 con dígito verificador
- **CUFE**: hash SHA-384 de 96 chars (Código Único Factura Electrónica DIAN)
- **Tipos DIAN**: 01=Factura venta, 91=Nota crédito, 92=Nota débito
- **IVA**: 19% general, 5%, 0% según producto
- **Retefuente**: 2.5% compras, 4% servicios, 11% honorarios
- **ReteIVA**: 15% del IVA (solo grandes contribuyentes)
- **ReteICA**: 4.14‰ Bogotá
- **NC (Nota Crédito)**: signo=-1 en todos los agregados de facturas_venta

## Funcionalidades implementadas

### Multi-contador
- Registro/login con bcrypt, sesiones Flask
- Cada contador ve solo sus empresas (`contador_id` en todas las tablas)
- Ownership validation en todos los endpoints

### Gmail automático
- OAuth2 por empresa, tokens encriptados en Supabase (`gmail_tokens`)
- Escaneo automático: detecta ZIPs DIAN (`z{NIT}`, `ad{NIT}`), XMLs, PDFs
- Regex DIAN permite espacios alrededor de punto y coma
- Retorna mejor resultado entre todos los adjuntos del correo
- Bandeja pendiente: muestra el correo Gmail de origen (`_email_origen`)

### Dashboard por empresa (subtabs)
- **Ventas / Gastos**: tablas con paginación, filtros, badges NC
- **Retenciones**: por cliente, signo correcto para NC
- **Declaraciones**: F-300 (IVA), F-350 (Retefuente), ICA, Renta estimada
- **Gmail**: configuración OAuth por empresa
- **Conciliar DIAN**: cruce con Excel del portal DIAN

### Declaraciones (F-300, F-350, ICA, Renta)
- **F-300**: IVA generado (ventas) vs IVA descontable (compras), por cuatrimestre
- **F-350**: Retefuente practicada, por mes
- **ICA**: Base ventas × 4.14‰, bimestral
- **Renta**: Estimación a partir de facturas + checklist de info faltante
- Aplica según régimen: `Juridica`, `GranContribuyente`, `responsable_iva`, `Natural`
- NC resta correctamente de todas las bases

### Excel descargable (6 hojas)
VENTAS · COMPRAS · IVA F-300 · RFTE 350 · ICA · RENTA

### Bandeja Pendiente
- Facturas cuya empresa no se pudo identificar por NIT
- Muestra correo Gmail de origen
- Deduplicación por NIT+numero; actualiza `_email_origen` si faltaba
- Asignación manual a empresa existente o creación de nueva

## Variables de entorno requeridas
```
FLASK_SECRET_KEY=...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
ENCRYPTION_KEY=...
```

## Memoria de sesión
**REGLA IMPORTANTE**: Solo guardar memoria cuando el usuario diga explícitamente
"guarda esto", "recuerda esto", o "memoria: [contenido]".
No guardar automáticamente nada de esta sesión sin autorización explícita.
Para invocar memoria guardada, el usuario debe decir "recuerda" o "carga memoria".

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
