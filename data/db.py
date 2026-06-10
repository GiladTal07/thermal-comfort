import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'readings.db')
RETENTION_DAYS = 90


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp     TEXT    NOT NULL,
                air_temp      REAL,
                humidity      REAL,
                mrt           REAL,
                air_speed     REAL,
                pmv           REAL,
                ppd           REAL,
                tsv           TEXT,
                notes         TEXT,
                blurry        INTEGER DEFAULT 0,
                sensor_fault  TEXT,
                photo_path    TEXT,
                thermal_path  TEXT
            )
        """)


def insert_reading(*, timestamp, air_temp, humidity, mrt, air_speed,
                   pmv, ppd, tsv, notes, blurry, sensor_fault,
                   photo_path, thermal_path):
    with _connect() as conn:
        conn.execute("""
            INSERT INTO readings
                (timestamp, air_temp, humidity, mrt, air_speed,
                 pmv, ppd, tsv, notes, blurry, sensor_fault,
                 photo_path, thermal_path)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (timestamp, air_temp, humidity, mrt, air_speed,
              pmv, ppd, tsv, notes, int(bool(blurry)),
              sensor_fault or None, photo_path, thermal_path))


def prune_old_readings():
    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime('%Y-%m-%d_%H-%M-%S')
    with _connect() as conn:
        conn.execute("DELETE FROM readings WHERE timestamp < ?", (cutoff,))


def get_latest():
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM readings ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def get_all():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM readings ORDER BY timestamp DESC"
        ).fetchall()
        return [dict(r) for r in rows]
