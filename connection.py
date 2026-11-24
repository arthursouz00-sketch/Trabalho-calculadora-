"""Conexão com o SQLite e criação/migração do esquema.

Cada operação abre uma conexão curta (``Database.connect``). Isso evita
problemas de concorrência, já que o Flet executa eventos em threads
diferentes, e garante que tudo é gravado em disco imediatamente.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name   TEXT    NOT NULL CHECK (length(trim(full_name)) >= 3),
    phone       TEXT    NOT NULL DEFAULT '',
    email       TEXT    NOT NULL DEFAULT '',
    birth_date  TEXT,                       -- AAAA-MM-DD
    address     TEXT    NOT NULL DEFAULT '',
    photo_file  TEXT,                       -- nome do arquivo em data/photos
    thumb_file  TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_people_name ON people(full_name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS appointments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL CHECK (length(trim(title)) > 0),
    description TEXT    NOT NULL DEFAULT '',
    date        TEXT    NOT NULL,           -- AAAA-MM-DD
    time        TEXT    NOT NULL,           -- HH:MM
    person_id   INTEGER REFERENCES people(id) ON DELETE SET NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(date, time);

CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT    NOT NULL CHECK (kind IN ('income', 'expense')),
    description  TEXT    NOT NULL CHECK (length(trim(description)) > 0),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    category     TEXT    NOT NULL,
    date         TEXT    NOT NULL,          -- AAAA-MM-DD
    source       TEXT    NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'whatsapp')),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);

CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id    TEXT    NOT NULL UNIQUE,  -- id da mensagem no provedor (wamid)
    direction      TEXT    NOT NULL CHECK (direction IN ('in', 'out')),
    sender         TEXT    NOT NULL,
    body           TEXT    NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'received'
                   CHECK (status IN ('received', 'pending', 'confirmed', 'discarded', 'ignored', 'sent')),
    transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS calc_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    expression  TEXT    NOT NULL,
    result      TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class DatabaseError(Exception):
    """Erro de banco apresentado ao usuário com mensagem amigável."""


class Database:
    """Fábrica de conexões SQLite com esquema garantido."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        self._init_lock = threading.Lock()
        self._initialized = False
        self.initialize()

    def initialize(self) -> None:
        with self._init_lock:
            if self._initialized:
                return
            with self.connect() as conn:
                conn.executescript(SCHEMA)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._initialized = True

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Abre uma conexão, faz commit no sucesso e rollback em caso de erro."""
        try:
            conn = sqlite3.connect(self.path, timeout=10)
        except sqlite3.Error as exc:  # pragma: no cover - falha de disco/permissão
            raise DatabaseError(f"Não foi possível abrir o banco de dados: {exc}") from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise DatabaseError(f"Dados inválidos para o banco: {exc}") from exc
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"Erro no banco de dados: {exc}") from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
