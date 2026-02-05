import sqlite3
from pathlib import Path

DB_PATH = Path("smartmirror.db")

def conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    with conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_name TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            k TEXT PRIMARY KEY,
            v TEXT NOT NULL
        )""")
        # 기본값
        defaults = {
            "avg_departure_hhmm": "08:10",
            "late_count_7days": "0",
            "rain_cnt": "0",
            "rain_umbrella_missed_cnt": "0",
            "miss_car_key": "0",
            "miss_wallet": "0",
            "miss_phone": "0",
            "miss_umbrella": "0",
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO stats(k,v) VALUES(?,?)", (k, v))

def get_stat(k: str, default: str = "0") -> str:
    with conn() as c:
        row = c.execute("SELECT v FROM stats WHERE k=?", (k,)).fetchone()
    return row[0] if row else default

def set_stat(k: str, v: str):
    with conn() as c:
        c.execute("INSERT INTO stats(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))

def log_event(ts_iso: str, event_name: str, metadata_json: str):
    with conn() as c:
        c.execute(
            "INSERT INTO events(ts,event_name,metadata_json) VALUES (?,?,?)",
            (ts_iso, event_name, metadata_json)
        )