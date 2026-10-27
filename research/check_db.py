import sqlite3
import os

db_path = r"C:\ProgramData\Tobii\Tobii Platform Runtime\IS5LEYETRACKER5\platform_runtime_database.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables:", [t[0] for t in tables])

for table in tables:
    tname = table[0]
    cursor.execute(f"SELECT * FROM {tname}")
    rows = cursor.fetchall()
    print(f"\n{tname}: {len(rows)} rows")
    for row in rows[:10]:
        print(f"  {row}")

conn.close()
