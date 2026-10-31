"""apply_procedure.py: re-create auto_match_requests() on the database in config.py."""
from db_sql import get_connection

with open("docker/mysql-init/01_schema.sql", encoding="utf-8") as f:
    sql = f.read()

start = sql.index("CREATE PROCEDURE auto_match_requests()")
end = sql.index("END //", start) + len("END //")
body = sql[start:end].replace("END //", "END")

conn = get_connection()
cur = conn.cursor()
cur.execute("DROP PROCEDURE IF EXISTS auto_match_requests")
cur.execute(body)
conn.commit()
cur.close()
conn.close()
print("procedure updated")