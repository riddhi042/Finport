import os
import sqlite3

DB = "data/crossborder.db"


def conn():
    os.makedirs("data", exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, event_type TEXT, capture_id TEXT,
            order_id TEXT, amount REAL, currency TEXT, status TEXT,
            payer_email TEXT, payer_country TEXT, created_at TEXT, raw TEXT)""")


def save(row):
    with conn() as c:
        c.execute("""INSERT OR IGNORE INTO events VALUES
            (:id,:event_type,:capture_id,:order_id,:amount,:currency,:status,
             :payer_email,:payer_country,:created_at,:raw)""", row)


def all_events():
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM events ORDER BY created_at DESC")]
