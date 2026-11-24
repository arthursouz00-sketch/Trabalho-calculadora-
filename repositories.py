"""Repositórios: única camada que escreve SQL.

Todas as consultas são parametrizadas (``?``) para evitar injeção de SQL.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from .connection import Database, DatabaseError
from .models import (
    EXPENSE,
    INCOME,
    Appointment,
    CalcEntry,
    ChatMessage,
    FinanceSummary,
    Person,
    Transaction,
)


def _d(value: Optional[str]) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def _t(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


class PersonRepository:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _row(row) -> Person:
        return Person(
            id=row["id"],
            full_name=row["full_name"],
            phone=row["phone"],
            email=row["email"],
            birth_date=_d(row["birth_date"]),
            address=row["address"],
            photo_file=row["photo_file"],
            thumb_file=row["thumb_file"],
            created_at=row["created_at"],
        )

    def add(self, p: Person) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                """INSERT INTO people (full_name, phone, email, birth_date, address, photo_file, thumb_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (p.full_name, p.phone, p.email,
                 p.birth_date.isoformat() if p.birth_date else None,
                 p.address, p.photo_file, p.thumb_file),
            )
            return int(cur.lastrowid)

    def update(self, p: Person) -> None:
        with self.db.connect() as conn:
            cur = conn.execute(
                """UPDATE people SET full_name=?, phone=?, email=?, birth_date=?, address=?,
                          photo_file=?, thumb_file=?, updated_at=datetime('now','localtime')
                   WHERE id=?""",
                (p.full_name, p.phone, p.email,
                 p.birth_date.isoformat() if p.birth_date else None,
                 p.address, p.photo_file, p.thumb_file, p.id),
            )
            if cur.rowcount == 0:
                raise DatabaseError("Pessoa não encontrada. Ela pode ter sido excluída.")

    def delete(self, person_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM people WHERE id=?", (person_id,))

    def get(self, person_id: int) -> Optional[Person]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()
        return self._row(row) if row else None

    def search(self, term: str = "") -> list[Person]:
        term = term.strip()
        with self.db.connect() as conn:
            if term:
                like = f"%{term}%"
                digits = "".join(ch for ch in term if ch.isdigit())
                rows = conn.execute(
                    """SELECT * FROM people
                       WHERE full_name LIKE ? COLLATE NOCASE OR email LIKE ? COLLATE NOCASE
                          OR address LIKE ? COLLATE NOCASE OR (? <> '' AND phone LIKE ?)
                       ORDER BY full_name COLLATE NOCASE""",
                    (like, like, like, digits, f"%{digits}%"),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM people ORDER BY full_name COLLATE NOCASE").fetchall()
        return [self._row(r) for r in rows]

    def count(self) -> int:
        with self.db.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]


class AppointmentRepository:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _row(row) -> Appointment:
        return Appointment(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            date=date.fromisoformat(row["date"]),
            time=_t(row["time"]),
            person_id=row["person_id"],
            person_name=row["person_name"],
        )

    _SELECT = """SELECT a.*, p.full_name AS person_name
                 FROM appointments a LEFT JOIN people p ON p.id = a.person_id"""

    def add(self, a: Appointment) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO appointments (title, description, date, time, person_id) VALUES (?, ?, ?, ?, ?)",
                (a.title, a.description, a.date.isoformat(), a.time.strftime("%H:%M"), a.person_id),
            )
            return int(cur.lastrowid)

    def update(self, a: Appointment) -> None:
        with self.db.connect() as conn:
            cur = conn.execute(
                """UPDATE appointments SET title=?, description=?, date=?, time=?, person_id=?,
                          updated_at=datetime('now','localtime') WHERE id=?""",
                (a.title, a.description, a.date.isoformat(), a.time.strftime("%H:%M"), a.person_id, a.id),
            )
            if cur.rowcount == 0:
                raise DatabaseError("Compromisso não encontrado. Ele pode ter sido excluído.")

    def delete(self, appointment_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM appointments WHERE id=?", (appointment_id,))

    def get(self, appointment_id: int) -> Optional[Appointment]:
        with self.db.connect() as conn:
            row = conn.execute(f"{self._SELECT} WHERE a.id=?", (appointment_id,)).fetchone()
        return self._row(row) if row else None

    def by_day(self, day: date) -> list[Appointment]:
        with self.db.connect() as conn:
            rows = conn.execute(
                f"{self._SELECT} WHERE a.date=? ORDER BY a.time, a.id", (day.isoformat(),)
            ).fetchall()
        return [self._row(r) for r in rows]

    def counts_between(self, start: date, end: date) -> dict[date, int]:
        """Quantidade de compromissos por dia no intervalo [start, end]."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT date, COUNT(*) AS n FROM appointments WHERE date BETWEEN ? AND ? GROUP BY date",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        return {date.fromisoformat(r["date"]): r["n"] for r in rows}

    def upcoming(self, from_day: date, limit: int = 5) -> list[Appointment]:
        with self.db.connect() as conn:
            rows = conn.execute(
                f"{self._SELECT} WHERE a.date >= ? ORDER BY a.date, a.time LIMIT ?",
                (from_day.isoformat(), limit),
            ).fetchall()
        return [self._row(r) for r in rows]


class TransactionRepository:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _row(row) -> Transaction:
        return Transaction(
            id=row["id"],
            kind=row["kind"],
            description=row["description"],
            amount_cents=row["amount_cents"],
            category=row["category"],
            date=date.fromisoformat(row["date"]),
            source=row["source"],
        )

    def add(self, t: Transaction) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                """INSERT INTO transactions (kind, description, amount_cents, category, date, source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (t.kind, t.description, t.amount_cents, t.category, t.date.isoformat(), t.source),
            )
            return int(cur.lastrowid)

    def update(self, t: Transaction) -> None:
        with self.db.connect() as conn:
            cur = conn.execute(
                """UPDATE transactions SET kind=?, description=?, amount_cents=?, category=?, date=?,
                          updated_at=datetime('now','localtime') WHERE id=?""",
                (t.kind, t.description, t.amount_cents, t.category, t.date.isoformat(), t.id),
            )
            if cur.rowcount == 0:
                raise DatabaseError("Lançamento não encontrado. Ele pode ter sido excluído.")

    def delete(self, transaction_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM transactions WHERE id=?", (transaction_id,))

    def get(self, transaction_id: int) -> Optional[Transaction]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM transactions WHERE id=?", (transaction_id,)).fetchone()
        return self._row(row) if row else None

    def list(self, start: Optional[date] = None, end: Optional[date] = None,
             kind: Optional[str] = None, term: str = "") -> list[Transaction]:
        sql = "SELECT * FROM transactions WHERE 1=1"
        args: list = []
        if start:
            sql += " AND date >= ?"
            args.append(start.isoformat())
        if end:
            sql += " AND date <= ?"
            args.append(end.isoformat())
        if kind in (INCOME, EXPENSE):
            sql += " AND kind = ?"
            args.append(kind)
        if term.strip():
            sql += " AND (description LIKE ? COLLATE NOCASE OR category LIKE ? COLLATE NOCASE)"
            args += [f"%{term.strip()}%"] * 2
        sql += " ORDER BY date DESC, id DESC"
        with self.db.connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._row(r) for r in rows]

    def summary(self, start: Optional[date] = None, end: Optional[date] = None) -> FinanceSummary:
        sql = """SELECT COALESCE(SUM(CASE WHEN kind='income' THEN amount_cents END), 0) AS inc,
                        COALESCE(SUM(CASE WHEN kind='expense' THEN amount_cents END), 0) AS exp
                 FROM transactions WHERE 1=1"""
        args: list = []
        if start:
            sql += " AND date >= ?"
            args.append(start.isoformat())
        if end:
            sql += " AND date <= ?"
            args.append(end.isoformat())
        with self.db.connect() as conn:
            row = conn.execute(sql, args).fetchone()
        return FinanceSummary(income_cents=row["inc"], expense_cents=row["exp"])

    def totals_by_category(self, kind: str, start: date, end: date) -> list[tuple[str, int]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT category, SUM(amount_cents) AS total FROM transactions
                   WHERE kind=? AND date BETWEEN ? AND ? GROUP BY category ORDER BY total DESC""",
                (kind, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [(r["category"], r["total"]) for r in rows]

    def monthly_totals(self, start: date, end: date) -> dict[str, FinanceSummary]:
        """Totais por mês ('AAAA-MM') no intervalo."""
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT substr(date, 1, 7) AS ym,
                          COALESCE(SUM(CASE WHEN kind='income' THEN amount_cents END), 0) AS inc,
                          COALESCE(SUM(CASE WHEN kind='expense' THEN amount_cents END), 0) AS exp
                   FROM transactions WHERE date BETWEEN ? AND ? GROUP BY ym""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        return {r["ym"]: FinanceSummary(r["inc"], r["exp"]) for r in rows}


class CalcHistoryRepository:
    MAX_ENTRIES = 200

    def __init__(self, db: Database):
        self.db = db

    def add(self, expression: str, result: str) -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT INTO calc_history (expression, result) VALUES (?, ?)", (expression, result))
            conn.execute(
                """DELETE FROM calc_history WHERE id NOT IN
                   (SELECT id FROM calc_history ORDER BY id DESC LIMIT ?)""",
                (self.MAX_ENTRIES,),
            )

    def recent(self, limit: int = 50) -> list[CalcEntry]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM calc_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [CalcEntry(r["expression"], r["result"], r["id"], r["created_at"]) for r in rows]

    def clear(self) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM calc_history")


class MessageRepository:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _row(r) -> ChatMessage:
        return ChatMessage(
            id=r["id"], external_id=r["external_id"], direction=r["direction"], sender=r["sender"],
            body=r["body"], status=r["status"], transaction_id=r["transaction_id"],
            created_at=r["created_at"],
        )

    def add(self, m: ChatMessage) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                """INSERT INTO whatsapp_messages (external_id, direction, sender, body, status, transaction_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (m.external_id, m.direction, m.sender, m.body, m.status, m.transaction_id),
            )
            return int(cur.lastrowid)

    def exists(self, external_id: str) -> bool:
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT 1 FROM whatsapp_messages WHERE external_id=?", (external_id,)
            ).fetchone() is not None

    def set_status(self, message_id: int, status: str, transaction_id: Optional[int] = None) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE whatsapp_messages SET status=?, transaction_id=COALESCE(?, transaction_id) WHERE id=?",
                (status, transaction_id, message_id),
            )

    def get(self, message_id: int) -> Optional[ChatMessage]:
        with self.db.connect() as conn:
            r = conn.execute("SELECT * FROM whatsapp_messages WHERE id=?", (message_id,)).fetchone()
        return self._row(r) if r else None

    def latest(self, sender: str, status: str, with_transaction: bool = False) -> Optional[ChatMessage]:
        """Mensagem recebida mais recente de um remetente com determinado status."""
        sql = "SELECT * FROM whatsapp_messages WHERE direction='in' AND sender=? AND status=?"
        if with_transaction:
            sql += " AND transaction_id IS NOT NULL"
        with self.db.connect() as conn:
            r = conn.execute(sql + " ORDER BY id DESC LIMIT 1", (sender, status)).fetchone()
        return self._row(r) if r else None

    def recent(self, limit: int = 100) -> list[ChatMessage]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM (SELECT * FROM whatsapp_messages ORDER BY id DESC LIMIT ?) ORDER BY id",
                (limit,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def clear(self) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM whatsapp_messages")


class SettingsRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str, default: str = "") -> str:
        with self.db.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
