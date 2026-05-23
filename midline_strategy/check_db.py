import sqlite3
from config import DB_PATH

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
for t in tables:
    c.execute(f"SELECT COUNT(*), MIN(date), MAX(date) FROM \"{t}\"")
    cnt, dmin, dmax = c.fetchone()
    print(f"{t}: {cnt} rows, {dmin} ~ {dmax}")
conn.close()
