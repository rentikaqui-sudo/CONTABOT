import sqlite3
conn = sqlite3.connect("data/demo.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for (t,) in tables:
    print(f"=== {t} ===")
    cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
    for c in cols:
        print(f"  {c[1]} {c[2]}")
    print()
conn.close()
