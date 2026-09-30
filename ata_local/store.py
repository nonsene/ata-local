import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from .config import DATA


@contextmanager
def connection():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / "queue.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA journal_mode=WAL")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def init():
    with connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS meetings (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, created REAL NOT NULL,
            status TEXT NOT NULL, stage TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
            detail TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
            meta TEXT NOT NULL, duration REAL NOT NULL DEFAULT 0)""")


def decode(row):
    if row is None:
        return None
    data = dict(row)
    data["meta"] = json.loads(data["meta"])
    return data


def create(title, meta):
    mid = uuid.uuid4().hex
    folder(mid).mkdir(parents=True)
    with connection() as db:
        db.execute("INSERT INTO meetings(id,title,created,status,stage,meta) VALUES(?,?,?,?,?,?)",
                   (mid, title, time.time(), "recording", "Gravando", json.dumps(meta, ensure_ascii=False)))
    return get(mid)


def folder(mid):
    if len(mid) != 32 or any(c not in "0123456789abcdef" for c in mid):
        raise ValueError("Identificador inválido")
    return DATA / "meetings" / mid


def get(mid):
    with connection() as db:
        return decode(db.execute("SELECT * FROM meetings WHERE id=?", (mid,)).fetchone())


def all_meetings():
    with connection() as db:
        return [decode(row) for row in db.execute("SELECT * FROM meetings ORDER BY created DESC")]


def update(mid, **fields):
    allowed = {"status", "stage", "progress", "detail", "error", "duration"}
    if not fields or set(fields) - allowed:
        raise ValueError("Campos inválidos")
    with connection() as db:
        db.execute("UPDATE meetings SET " + ",".join(f"{key}=?" for key in fields) + " WHERE id=?",
                   [*fields.values(), mid])


def claim():
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM meetings WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
        if row:
            db.execute("UPDATE meetings SET status='processing',error='' WHERE id=?", (row["id"],))
            return decode(row)


def recover():
    with connection() as db:
        db.execute("""UPDATE meetings SET status='queued',stage='Retomando',detail='Retomada após interrupção'
                      WHERE status='processing'""")
        db.execute("UPDATE meetings SET status='cancelled',stage='Cancelado' WHERE status='cancelling'")
        db.execute("""UPDATE meetings SET status='interrupted',stage='Gravação interrompida',
                      error='O aplicativo foi fechado durante a captura. Recupere o áudio parcial.'
                      WHERE status IN ('recording','paused')""")


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
