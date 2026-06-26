"""
setup_supabase.py — Migra datos de SQLite a Supabase.
"""
import os, sqlite3
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]
DB_PATH = Path(__file__).parent.parent / "data" / "demo.db"

sb = create_client(URL, KEY)

def migrar_empresas(conn):
    print("Migrando empresas_clientes...")
    rows = conn.execute("SELECT * FROM empresas_clientes").fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM empresas_clientes LIMIT 0").description]
    count, errors = 0, 0
    for row in rows:
        data = dict(zip(cols, row))
        data.pop("id", None)
        try:
            sb.table("empresas_clientes").upsert(data, on_conflict="nit").execute()
            count += 1
        except Exception as e:
            print(f"  Error {data.get('nit')}: {str(e)[:80]}")
            errors += 1
    print(f"  {count} OK, {errors} errores\n")

def migrar_facturas_venta(conn):
    print("Migrando facturas_venta...")
    rows = conn.execute("SELECT * FROM facturas_venta").fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM facturas_venta LIMIT 0").description]
    count, errors = 0, 0
    for row in rows:
        data = dict(zip(cols, row))
        data.pop("id", None)
        data["gran_contribuyente"] = bool(data.get("gran_contribuyente", 0))
        data["fuente"] = "demo"
        for f in ("fecha", "fecha_vencimiento"):
            if not data.get(f):
                data[f] = None
        try:
            sb.table("facturas_venta").upsert(data, on_conflict="empresa_id,numero").execute()
            count += 1
        except Exception as e:
            print(f"  Error {data.get('numero')}: {str(e)[:80]}")
            errors += 1
    print(f"  {count} OK, {errors} errores\n")

def migrar_facturas_gastos(conn):
    print("Migrando facturas_gastos...")
    rows = conn.execute("SELECT * FROM facturas_gastos").fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM facturas_gastos LIMIT 0").description]
    count, errors = 0, 0
    for row in rows:
        data = dict(zip(cols, row))
        data.pop("id", None)
        data["fuente"] = "demo"
        for f in ("fecha", "fecha_vencimiento"):
            if not data.get(f):
                data[f] = None
        try:
            sb.table("facturas_gastos").upsert(data, on_conflict="empresa_id,numero").execute()
            count += 1
        except Exception as e:
            print(f"  Error {data.get('numero')}: {str(e)[:80]}")
            errors += 1
    print(f"  {count} OK, {errors} errores\n")

if __name__ == "__main__":
    print(f"Conectando a {URL}...\n")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    migrar_empresas(conn)
    migrar_facturas_venta(conn)
    migrar_facturas_gastos(conn)
    conn.close()

    print("Verificando...")
    r = sb.table("empresas_clientes").select("id", count="exact").execute()
    print(f"  Empresas:        {r.count}")
    r = sb.table("facturas_venta").select("id", count="exact").execute()
    print(f"  Facturas venta:  {r.count}")
    r = sb.table("facturas_gastos").select("id", count="exact").execute()
    print(f"  Facturas gastos: {r.count}")
    print("\nMigracion completa.")
