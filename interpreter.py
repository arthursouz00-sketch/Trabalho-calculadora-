"""Interpretador de mensagens em linguagem natural -> sugestão de lançamento.

Baseado em regras (expressões regulares + palavras-chave), funciona offline
e de forma determinística. Exemplo:

    "Gastei R$ 45,00 no mercado hoje"
    -> Despesa | Alimentação | R$ 45,00 | "Mercado" | data de hoje
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.database.models import EXPENSE, INCOME, TransactionSuggestion


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _norm(text: str) -> str:
    return _strip_accents(text.lower())


INCOME_VERBS = ["recebi", "ganhei", "entrou", "caiu", "vendi", "receita", "entrada", "faturei",
                "me pagaram", "me pagou", "depositaram", "deposito recebido", "pix recebido", "rendeu", "rendimento"]
EXPENSE_VERBS = ["gastei", "paguei", "comprei", "despesa", "saida", "gasto", "pagamento", "transferi",
                 "pix para", "pix pro", "pix pra", "debito", "boleto", "conta de", "fatura"]

# categoria -> palavras-chave (sem acento, minúsculas)
EXPENSE_KEYWORDS: dict[str, list[str]] = {
    "Alimentação": ["mercado", "supermercado", "restaurante", "lanche", "ifood", "padaria", "almoco", "jantar",
                    "comida", "pizza", "acougue", "feira", "hortifruti", "cafe", "sorvete", "hamburguer", "marmita",
                    "delivery", "bebida"],
    "Transporte": ["uber", "99", "taxi", "gasolina", "combustivel", "etanol", "onibus", "metro", "estacionamento",
                   "pedagio", "passagem", "oficina", "mecanico", "ipva", "carro", "moto", "bilhete unico"],
    "Moradia": ["aluguel", "condominio", "iptu", "reforma", "moveis", "faxina", "diarista"],
    "Contas e serviços": ["luz", "energia", "agua", "gas", "internet", "telefone", "celular", "plano", "tv a cabo",
                          "fatura do cartao", "cartao de credito", "boleto"],
    "Saúde": ["farmacia", "remedio", "medico", "consulta", "dentista", "exame", "hospital", "plano de saude",
              "academia", "psicologo", "terapia"],
    "Lazer": ["cinema", "show", "netflix", "spotify", "streaming", "viagem", "hotel", "bar", "jogo", "games",
              "ingresso", "passeio", "festa", "balada"],
    "Educação": ["curso", "faculdade", "escola", "livro", "livros", "mensalidade", "material escolar", "apostila"],
    "Compras": ["roupa", "roupas", "loja", "shopping", "presente", "presentes", "amazon", "mercado livre",
                "sapato", "tenis", "eletronico", "natal", "enfeite", "enfeites"],
}
INCOME_KEYWORDS: dict[str, list[str]] = {
    "Salário": ["salario", "pagamento do mes", "holerite", "13o", "decimo terceiro", "ferias", "adiantamento"],
    "Serviços": ["freela", "freelance", "servico", "bico", "consultoria", "projeto", "aula particular"],
    "Vendas": ["venda", "vendi", "vendas"],
    "Investimentos": ["investimento", "dividendo", "dividendos", "rendimento", "rendeu", "juros", "cdb", "tesouro"],
    "Presentes": ["presente", "mesada", "ganhei de"],
}

MONEY_RE = re.compile(
    r"(?:r\$\s*)?(?<![\d/])(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)(?![\d/])(\s*(?:mil|reais|real|conto|contos|k)\b)?",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
DAY_RE = re.compile(r"\bdia\s+(\d{1,2})\b")

STOPWORDS = {"no", "na", "nos", "nas", "em", "de", "do", "da", "dos", "das", "com", "pro", "pra", "para", "o",
             "a", "os", "as", "um", "uma", "e", "hoje", "ontem", "anteontem", "reais", "real", "r$", "mil", "pix",
             "via", "por", "meu", "minha", "dia", "conto", "contos", "k", "que", "eu", "foi", "agora"}
LEADING_WORDS = set(INCOME_VERBS + EXPENSE_VERBS) | {"gastar", "pagar", "comprar", "receber"}


def parse_amount(text: str) -> Optional[int]:
    """Primeiro valor monetário da mensagem, em centavos."""
    norm = text.lower()
    for match in MONEY_RE.finditer(norm):
        raw, suffix = match.group(1), (match.group(2) or "").strip()
        # ignora números que fazem parte de datas ("dia 15") ou horários
        before = norm[max(0, match.start() - 4):match.start()]
        if "dia " in before and not norm[match.start():match.end()].startswith("r$"):
            continue
        if "," in raw:
            value_txt = raw.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):
            value_txt = raw.replace(".", "")
        else:
            value_txt = raw
        try:
            value = Decimal(value_txt)
        except InvalidOperation:
            continue
        if suffix in ("mil", "k"):
            value *= 1000
        if value <= 0:
            continue
        return int((value * 100).quantize(Decimal("1")))
    return None


def parse_date(text: str, today: date) -> date:
    norm = _norm(text)
    if "anteontem" in norm:
        return today - timedelta(days=2)
    if "ontem" in norm:
        return today - timedelta(days=1)
    m = DATE_RE.search(norm)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            pass
    m = DAY_RE.search(norm)
    if m:
        try:
            candidate = today.replace(day=int(m.group(1)))
            return candidate
        except ValueError:
            pass
    return today


def _find_category(norm: str, table: dict[str, list[str]]) -> tuple[Optional[str], Optional[str]]:
    best: tuple[Optional[str], Optional[str], int] = (None, None, 0)
    for category, words in table.items():
        for word in words:
            if re.search(rf"\b{re.escape(word)}\b", norm) and len(word) > best[2]:
                best = (category, word, len(word))
    return best[0], best[1]


def _description(original: str, keyword: Optional[str]) -> str:
    text = re.sub(r"r\$\s*", " ", original, flags=re.IGNORECASE)
    text = MONEY_RE.sub(" ", text)
    text = DATE_RE.sub(" ", text)
    text = re.sub(r"[^\wÀ-ÿ\s]", " ", text)
    words = text.split()
    # remove verbos iniciais e palavras de ligação
    while words and (_norm(words[0]) in LEADING_WORDS or _norm(words[0]) in STOPWORDS):
        words.pop(0)
    kept = [w for w in words if _norm(w) not in STOPWORDS and _norm(w) not in LEADING_WORDS]
    if kept:
        desc = " ".join(kept[:5])
        return desc[0].upper() + desc[1:]
    if keyword:
        return keyword.capitalize()
    return "Lançamento via WhatsApp"


def interpret(text: str, today: Optional[date] = None) -> Optional[TransactionSuggestion]:
    """Retorna a sugestão de lançamento ou ``None`` se não houver valor na mensagem."""
    today = today or date.today()
    if not text or not text.strip():
        return None
    norm = _norm(text)
    amount = parse_amount(text)
    if amount is None:
        return None

    notes: list[str] = []
    confidence = 0.4
    is_income = any(re.search(rf"\b{re.escape(v)}\b", norm) for v in INCOME_VERBS)
    is_expense = any(re.search(rf"\b{re.escape(v)}\b", norm) for v in EXPENSE_VERBS)
    inc_cat, inc_kw = _find_category(norm, INCOME_KEYWORDS)
    exp_cat, exp_kw = _find_category(norm, EXPENSE_KEYWORDS)

    if is_income and not is_expense:
        kind, confidence = INCOME, confidence + 0.3
    elif is_expense and not is_income:
        kind, confidence = EXPENSE, confidence + 0.3
    elif inc_cat and not exp_cat:
        kind = INCOME
        confidence += 0.15
    else:
        kind = EXPENSE
        notes.append("Tipo não identificado com certeza; considerado despesa.")

    if kind == INCOME:
        category, keyword = inc_cat, inc_kw
    else:
        category, keyword = exp_cat, exp_kw
    if category:
        confidence += 0.25
    else:
        category = "Outros"
        notes.append("Categoria não reconhecida; usada 'Outros'.")

    return TransactionSuggestion(
        kind=kind,
        category=category,
        amount_cents=amount,
        description=_description(text, keyword)[:100],
        date=parse_date(text, today),
        confidence=round(min(confidence, 0.95), 2),
        notes=notes,
    )
