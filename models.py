"""Modelos de domínio (dataclasses) usados entre banco, serviços e interface."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time  # noqa: F401  (time usado em anotações)
from typing import Optional

INCOME = "income"
EXPENSE = "expense"


@dataclass
class Person:
    full_name: str
    phone: str = ""
    email: str = ""
    birth_date: Optional[date] = None
    address: str = ""
    photo_file: Optional[str] = None
    thumb_file: Optional[str] = None
    id: Optional[int] = None
    created_at: str = ""

    def age(self, today: Optional[date] = None) -> Optional[int]:
        if not self.birth_date:
            return None
        today = today or date.today()
        years = today.year - self.birth_date.year
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years

    def has_birthday_on(self, day: date) -> bool:
        if not self.birth_date:
            return False
        bd = self.birth_date
        if bd.month == 2 and bd.day == 29 and not _is_leap(day.year):
            return day.month == 2 and day.day == 28
        return (bd.month, bd.day) == (day.month, day.day)

    @property
    def initials(self) -> str:
        parts = [p for p in self.full_name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


@dataclass
class Appointment:
    title: str
    date: date
    time: time
    description: str = ""
    person_id: Optional[int] = None
    person_name: Optional[str] = None  # preenchido via JOIN, somente leitura
    id: Optional[int] = None


@dataclass
class Transaction:
    kind: str  # INCOME ou EXPENSE
    description: str
    amount_cents: int
    category: str
    date: date
    source: str = "manual"
    id: Optional[int] = None

    @property
    def is_income(self) -> bool:
        return self.kind == INCOME

    @property
    def signed_cents(self) -> int:
        return self.amount_cents if self.is_income else -self.amount_cents


@dataclass
class FinanceSummary:
    income_cents: int = 0
    expense_cents: int = 0

    @property
    def balance_cents(self) -> int:
        return self.income_cents - self.expense_cents


@dataclass
class CalcEntry:
    expression: str
    result: str
    id: Optional[int] = None
    created_at: str = ""


@dataclass
class ChatMessage:
    external_id: str
    direction: str  # 'in' (recebida) ou 'out' (resposta da automação)
    sender: str
    body: str
    status: str = "received"
    transaction_id: Optional[int] = None
    id: Optional[int] = None
    created_at: str = ""


@dataclass
class TransactionSuggestion:
    """Sugestão de lançamento produzida pelo interpretador de mensagens."""

    kind: str
    category: str
    amount_cents: int
    description: str
    date: date
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)
