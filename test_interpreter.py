from datetime import date

from app.database.models import EXPENSE, INCOME
from app.services.whatsapp.interpreter import interpret, parse_amount

TODAY = date(2026, 12, 20)


def test_example_from_spec():
    s = interpret("Gastei R$ 45,00 no mercado hoje.", TODAY)
    assert (s.kind, s.category, s.amount_cents, s.description, s.date) == (EXPENSE, "Alimentação", 4500, "Mercado", TODAY)


def test_income_salary():
    s = interpret("Recebi 3.500 de salário", TODAY)
    assert (s.kind, s.category, s.amount_cents) == (INCOME, "Salário", 350000)


def test_yesterday_bill():
    s = interpret("Paguei 120,50 da conta de luz ontem", TODAY)
    assert s.kind == EXPENSE and s.category == "Contas e serviços" and s.amount_cents == 12050
    assert s.date == date(2026, 12, 19)


def test_transport_and_explicit_date():
    s = interpret("uber 23,90 dia 15", TODAY)
    assert s.category == "Transporte" and s.amount_cents == 2390 and s.date == date(2026, 12, 15)
    s = interpret("Comprei presentes de natal 250 em 18/12", TODAY)
    assert s.category == "Compras" and s.date == date(2026, 12, 18) and s.amount_cents == 25000


def test_mil_suffix_and_no_amount():
    assert parse_amount("vendi a bike por 2 mil") == 200000
    assert interpret("bom dia, tudo bem?", TODAY) is None
