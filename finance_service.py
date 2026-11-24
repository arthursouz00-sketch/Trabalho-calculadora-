"""Regras de negócio da gestão financeira."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.database.models import EXPENSE, INCOME, FinanceSummary, Transaction
from app.database.repositories import TransactionRepository
from app.services.appointment_service import shift_month
from app.utils.validators import ValidationError, parse_date_br, parse_money, required

EXPENSE_CATEGORIES = ["Alimentação", "Transporte", "Moradia", "Saúde", "Lazer",
                      "Educação", "Compras", "Contas e serviços", "Outros"]
INCOME_CATEGORIES = ["Salário", "Serviços", "Vendas", "Investimentos", "Presentes", "Outros"]


def categories_for(kind: str) -> list[str]:
    return INCOME_CATEGORIES if kind == INCOME else EXPENSE_CATEGORIES


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


@dataclass
class MonthBar:
    label: str
    income_cents: int
    expense_cents: int


class FinanceService:
    def __init__(self, repo: TransactionRepository):
        self.repo = repo

    @staticmethod
    def build(kind: str, description: str, amount: str, category: str, day: str | date,
              transaction_id: Optional[int] = None, source: str = "manual") -> Transaction:
        if kind not in (INCOME, EXPENSE):
            raise ValidationError("Escolha entre entrada ou despesa.", "kind")
        description = required(description, "a descrição", "description")
        if len(description) > 100:
            raise ValidationError("Descrição muito longa (máximo 100 caracteres).", "description")
        cents = parse_money(amount, "amount")
        if category not in categories_for(kind):
            raise ValidationError("Selecione uma categoria.", "category")
        when = day if isinstance(day, date) else parse_date_br(day, "date")
        return Transaction(id=transaction_id, kind=kind, description=description,
                           amount_cents=cents, category=category, date=when, source=source)

    def save(self, t: Transaction) -> Transaction:
        if t.id:
            self.repo.update(t)
        else:
            t.id = self.repo.add(t)
        return t

    def delete(self, transaction_id: int) -> None:
        self.repo.delete(transaction_id)

    def get(self, transaction_id: int) -> Optional[Transaction]:
        return self.repo.get(transaction_id)

    def list_month(self, year: int, month: int, kind: Optional[str] = None, term: str = "") -> list[Transaction]:
        start, end = month_bounds(year, month)
        return self.repo.list(start, end, kind, term)

    def overall(self) -> FinanceSummary:
        """Saldo atual: todos os lançamentos até hoje (inclusive)."""
        return self.repo.summary(end=date.today())

    def month_summary(self, year: int, month: int) -> FinanceSummary:
        return self.repo.summary(*month_bounds(year, month))

    def expenses_by_category(self, year: int, month: int) -> list[tuple[str, int]]:
        return self.repo.totals_by_category(EXPENSE, *month_bounds(year, month))

    def last_months(self, year: int, month: int, count: int = 6) -> list[MonthBar]:
        from app.utils.formatters import MONTHS_SHORT
        first_y, first_m = shift_month(year, month, -(count - 1))
        start = date(first_y, first_m, 1)
        end = month_bounds(year, month)[1]
        totals = self.repo.monthly_totals(start, end)
        bars = []
        for i in range(count):
            y, m = shift_month(first_y, first_m, i)
            s = totals.get(f"{y:04d}-{m:02d}", FinanceSummary())
            bars.append(MonthBar(MONTHS_SHORT[m - 1].capitalize(), s.income_cents, s.expense_cents))
        return bars
