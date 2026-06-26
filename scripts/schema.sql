-- ContaBot Schema completo
-- Pegar en Supabase SQL Editor y ejecutar (nuevo proyecto)

CREATE TABLE IF NOT EXISTS contadores (
    id             SERIAL PRIMARY KEY,
    email          TEXT UNIQUE NOT NULL,
    password_hash  TEXT NOT NULL,
    nombre         TEXT NOT NULL,
    tp_numero      TEXT DEFAULT '',
    estudio_nombre TEXT DEFAULT '',
    telefono       TEXT DEFAULT '',
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS empresas_clientes (
    id          SERIAL PRIMARY KEY,
    contador_id INTEGER REFERENCES contadores(id),
    razon_social TEXT NOT NULL,
    nit         TEXT UNIQUE NOT NULL,
    sector      TEXT,
    ciudad      TEXT,
    direccion   TEXT,
    contacto    TEXT,
    email       TEXT,
    telefono    TEXT,
    regimen     TEXT,
    color       TEXT,
    icono       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS facturas_venta (
    id                  SERIAL PRIMARY KEY,
    empresa_id          INTEGER REFERENCES empresas_clientes(id),
    numero              TEXT NOT NULL,
    cufe                TEXT,
    fecha               DATE,
    fecha_vencimiento   DATE,
    cliente_nit         TEXT,
    cliente_nombre      TEXT,
    cliente_ciudad      TEXT,
    gran_contribuyente  BOOLEAN DEFAULT FALSE,
    subtotal            NUMERIC(18,2) DEFAULT 0,
    iva                 NUMERIC(18,2) DEFAULT 0,
    retefuente          NUMERIC(18,2) DEFAULT 0,
    reteiva             NUMERIC(18,2) DEFAULT 0,
    reteica             NUMERIC(18,2) DEFAULT 0,
    total_factura       NUMERIC(18,2) DEFAULT 0,
    valor_neto          NUMERIC(18,2) DEFAULT 0,
    estado              TEXT DEFAULT 'PENDIENTE',
    archivo_pdf         TEXT,
    fuente              TEXT DEFAULT 'manual',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(empresa_id, numero)
);

CREATE TABLE IF NOT EXISTS facturas_gastos (
    id                  SERIAL PRIMARY KEY,
    empresa_id          INTEGER REFERENCES empresas_clientes(id),
    numero              TEXT NOT NULL,
    cufe                TEXT,
    fecha               DATE,
    fecha_vencimiento   DATE,
    proveedor_nit       TEXT,
    proveedor_nombre    TEXT,
    proveedor_ciudad    TEXT,
    categoria           TEXT,
    subtotal            NUMERIC(18,2) DEFAULT 0,
    iva                 NUMERIC(18,2) DEFAULT 0,
    retefuente          NUMERIC(18,2) DEFAULT 0,
    reteiva             NUMERIC(18,2) DEFAULT 0,
    reteica             NUMERIC(18,2) DEFAULT 0,
    total_factura       NUMERIC(18,2) DEFAULT 0,
    valor_neto          NUMERIC(18,2) DEFAULT 0,
    estado              TEXT DEFAULT 'PENDIENTE',
    archivo_pdf         TEXT,
    fuente              TEXT DEFAULT 'manual',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(empresa_id, numero)
);

CREATE TABLE IF NOT EXISTS empresas_pendientes (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    contador_id INTEGER REFERENCES contadores(id),
    nit         TEXT,
    razon_social TEXT,
    ciudad      TEXT,
    factura_data JSONB,
    fuente      TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS obligaciones_completadas (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    empresa_id  INTEGER,
    tipo        TEXT,
    vencimiento DATE,
    realizada_en DATE DEFAULT CURRENT_DATE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(empresa_id, tipo, vencimiento)
);

-- Token OAuth de Gmail por empresa (se renueva cada 7 días en modo Testing)
CREATE TABLE IF NOT EXISTS gmail_tokens (
    id               SERIAL PRIMARY KEY,
    empresa_id       INTEGER REFERENCES empresas_clientes(id) ON DELETE CASCADE,
    email            TEXT NOT NULL,
    refresh_token    TEXT NOT NULL,
    token_created_at TIMESTAMPTZ DEFAULT NOW(),
    activo           BOOLEAN DEFAULT TRUE,
    history_id       TEXT,
    watch_expires    TEXT,
    UNIQUE(empresa_id)
);
