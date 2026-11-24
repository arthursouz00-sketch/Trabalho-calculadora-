"""Validação e conversão de entradas digitadas pelo usuário.

Cada função devolve o valor convertido ou levanta ``ValidationError`` com
mensagem pronta para ser exibida na interface.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation


class ValidationError(ValueError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def required(value: str, label: str, field: str | None = None, min_len: int = 1) -> str:
    value = (value or "").strip()
    if not value:
        raise ValidationError(f"Informe {label}.", field)
    if len(value) < min_len:
        raise ValidationError(f"{label.capitalize()} deve ter pelo menos {min_len} caracteres.", field)
    return value


def parse_date_br(value: str, field: str | None = None, allow_empty: bool = False) -> date | None:
    value = (value or "").strip()
    if not value:
        if allow_empty:
            return None
        raise ValidationError("Informe a data.", field)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValidationError("Data inválida. Use o formato DD/MM/AAAA.", field)


def parse_time(value: str, field: str | None = None) -> time:
    value = (value or "").strip().lower().replace("h", ":").rstrip(":")
    if re.fullmatch(r"\d{1,2}", value):
        value += ":00"
    if re.fullmatch(r"\d{3,4}", value):
        value = value[:-2] + ":" + value[-2:]
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        raise ValidationError("Horário inválido. Use HH:MM (ex.: 14:30).", field) from None


def validate_email(value: str, field: str | None = None) -> str:
    value = (value or "").strip()
    if value and not EMAIL_RE.match(value):
        raise ValidationError("E-mail inválido. Exemplo: nome@dominio.com", field)
    return value.lower()


def validate_phone(value: str, field: str | None = None) -> str:
    """Aceita telefones brasileiros com DDD (10 ou 11 dígitos). Retorna só dígitos."""
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if not digits:
        return ""
    if len(digits) not in (10, 11):
        raise ValidationError("Telefone deve ter DDD + número (10 ou 11 dígitos).", field)
    return digits


def parse_money(value: str, field: str | None = None) -> int:
    """Converte '1.234,56', 'R$ 45', '45.90' em centavos (int > 0)."""
    txt = (value or "").strip().replace("R$", "").replace(" ", "")
    if not txt:
        raise ValidationError("Informe o valor.", field)
    if "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", txt):
        txt = txt.replace(".", "")
    try:
        amount = Decimal(txt)
    except InvalidOperation:
        raise ValidationError("Valor inválido. Exemplo: 1.234,56", field) from None
    if amount <= 0:
        raise ValidationError("O valor deve ser maior que zero.", field)
    if amount > Decimal("999999999.99"):
        raise ValidationError("Valor muito alto.", field)
    return int((amount * 100).quantize(Decimal("1")))
