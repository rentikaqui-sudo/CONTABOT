-- Migración: agregar sistema multi-contador a ContaBot
-- Ejecutar en Supabase SQL Editor sobre proyecto existente

-- 1. Tabla de usuarios/contadores
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

-- 2. Agregar contador_id a empresas_clientes
ALTER TABLE empresas_clientes
    ADD COLUMN IF NOT EXISTS contador_id INTEGER REFERENCES contadores(id);

-- 3. Agregar contador_id a empresas_pendientes (inbox por contador)
ALTER TABLE empresas_pendientes
    ADD COLUMN IF NOT EXISTS contador_id INTEGER REFERENCES contadores(id);

-- 4. Índices críticos faltantes
CREATE INDEX IF NOT EXISTS idx_ec_contador       ON empresas_clientes(contador_id);
CREATE INDEX IF NOT EXISTS idx_fv_empresa_estado ON facturas_venta(empresa_id, estado);
CREATE INDEX IF NOT EXISTS idx_fg_empresa_estado ON facturas_gastos(empresa_id, estado);
CREATE INDEX IF NOT EXISTS idx_fv_empresa_fecha  ON facturas_venta(empresa_id, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_fg_empresa_fecha  ON facturas_gastos(empresa_id, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_ec_nit            ON empresas_clientes(nit);
CREATE INDEX IF NOT EXISTS idx_fg_cufe           ON facturas_gastos(cufe);

-- 5. FK faltante en obligaciones_completadas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_oc_empresa'
    ) THEN
        ALTER TABLE obligaciones_completadas
            ADD CONSTRAINT fk_oc_empresa
            FOREIGN KEY (empresa_id) REFERENCES empresas_clientes(id);
    END IF;
END $$;

-- 6. Tipos de documento DIAN en facturas_venta y facturas_gastos
--
-- tipo_documento: factura | nota_credito | nota_debito | doc_equivalente | doc_soporte | nota_ajuste_ds
-- tipo_dian:      01 | 02 | 03 | 04 | 05 | 06 | 91 | 92
-- referencia_nc:  número de la factura original que anula (solo NC/ND)
--
-- Combinaciones posibles:
--   facturas_venta  + factura       = venta normal (01, 02, 04)
--   facturas_venta  + nota_credito  = VIR devuelve plata a su cliente (91, empresa=proveedor)
--   facturas_venta  + nota_debito   = VIR cobra extra a su cliente (92, empresa=proveedor)
--   facturas_gastos + factura       = compra normal (01, 02, 04)
--   facturas_gastos + nota_credito  = proveedor devuelve plata a empresa (91, empresa=receptor)
--   facturas_gastos + nota_debito   = proveedor cobra extra a empresa (92, empresa=receptor)
--   facturas_gastos + doc_equivalente = tiquete, recibo de caja, pasaje (03, siempre gasto)
--   facturas_gastos + doc_soporte   = compra a agricultor/persona natural no obligada (05)
--   facturas_gastos + nota_ajuste_ds = ajuste al doc soporte (06)

ALTER TABLE facturas_venta
    ADD COLUMN IF NOT EXISTS tipo_documento TEXT DEFAULT 'factura',
    ADD COLUMN IF NOT EXISTS tipo_dian      TEXT DEFAULT '01',
    ADD COLUMN IF NOT EXISTS referencia_nc  TEXT;

ALTER TABLE facturas_gastos
    ADD COLUMN IF NOT EXISTS tipo_documento TEXT DEFAULT 'factura',
    ADD COLUMN IF NOT EXISTS tipo_dian      TEXT DEFAULT '01',
    ADD COLUMN IF NOT EXISTS referencia_nc  TEXT;

-- 7. Índice en cufe de facturas_venta también
CREATE INDEX IF NOT EXISTS idx_fv_cufe ON facturas_venta(cufe);

-- 8. gmail_tokens: columnas para Gmail Push (Pub/Sub)
ALTER TABLE gmail_tokens
    ADD COLUMN IF NOT EXISTS history_id    TEXT,
    ADD COLUMN IF NOT EXISTS watch_expires TEXT;
