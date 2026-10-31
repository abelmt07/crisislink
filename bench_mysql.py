"""bench_mysql.py: separates network round trips from query time."""
import time

from db_sql import get_connection

conn = get_connection()
cur = conn.cursor()

for label, fn in (
    ("ping", lambda: conn.ping()),
    ("SELECT 1", lambda: (cur.execute("SELECT 1"), cur.fetchall())),
    ("view", lambda: (cur.execute("SELECT * FROM v_situation_report"), cur.fetchall())),
):
    for _ in range(3):
        t0 = time.perf_counter()
        fn()
        print(f"{label:10} {(time.perf_counter() - t0) * 1000:7.0f} ms")

cur.close()
conn.close()