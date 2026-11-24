"""Formatação no padrão brasileiro (moeda, datas, números, telefone)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]
MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
            "sexta-feira", "sábado", "domingo"]
WEEKDAYS_SHORT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def money(cents: int, signed: bool = False) -> str:
    """12345 -> 'R$ 123,45'. Com ``signed`` acrescenta '+' a valores positivos."""
    negative = cents < 0
    value = abs(cents)
    reais, cent = divmod(value, 100)
    reais_txt = f"{reais:,}".replace(",", ".")
    txt = f"R$ {reais_txt},{cent:02d}"
    if negative:
        return f"− {txt}"
    if signed and cents > 0:
        return f"+ {txt}"
    return txt


def date_br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def date_long(d: date) -> str:
    """'terça-feira, 24 de novembro de 2026'"""
    return f"{WEEKDAYS[d.weekday()]}, {d.day} de {MONTHS[d.month - 1]} de {d.year}"


def date_medium(d: date) -> str:
    """'24 de novembro'"""
    return f"{d.day} de {MONTHS[d.month - 1]}"


def month_year(year: int, month: int) -> str:
    return f"{MONTHS[month - 1].capitalize()} de {year}"


def number_br(value: Decimal | int | float, max_decimals: int = 10, grouping: bool = True) -> str:
    """Formata número com vírgula decimal, removendo zeros à direita."""
    d = Decimal(str(value)) if not isinstance(value, Decimal) else value
    if d == d.to_integral_value() and abs(d) < Decimal("1e21"):
        txt = f"{int(d):,}" if grouping else f"{int(d)}"
        return txt.replace(",", ".")
    quant = Decimal(1).scaleb(-max_decimals)
    d = d.quantize(quant).normalize()
    sign = "-" if d < 0 else ""
    d = abs(d)
    if d.adjusted() >= 21 or d.adjusted() < -max_decimals:
        txt = f"{d:.6e}".replace(".", ",")
        return sign + txt
    int_part, _, frac = f"{d:f}".partition(".")
    int_txt = f"{int(int_part):,}".replace(",", ".") if grouping else int_part
    return sign + int_txt + ("," + frac if frac else "")


def phone_br(digits: str) -> str:
    """'11987654321' -> '(11) 98765-4321'."""
    d = "".join(ch for ch in digits if ch.isdigit())
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return digits
