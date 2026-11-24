"""Motor da calculadora: avalia expressões com segurança, sem ``eval()``.

A expressão é convertida em árvore sintática (``ast``) e somente números e
operadores matemáticos permitidos são avaliados, usando ``Decimal`` para
evitar erros de arredondamento (0,1 + 0,2 = 0,3).
"""
from __future__ import annotations

import ast
import re
from decimal import Decimal, DivisionByZero, InvalidOperation, Overflow, localcontext

from app.utils.formatters import number_br


class CalculatorError(ValueError):
    """Erro com mensagem amigável para o usuário."""


DISPLAY_TO_PY = {"×": "*", "÷": "/", "−": "-", "^": "**", ",": "."}
MAX_EXPONENT = 1000
MAX_LENGTH = 200


def normalize(expression: str) -> str:
    """Converte símbolos de exibição para sintaxe Python."""
    expr = expression.strip()
    # "1.234,5" (milhar com ponto) não é aceito no visor; ponto também vale como decimal
    for k, v in DISPLAY_TO_PY.items():
        expr = expr.replace(k, v)
    expr = expr.replace("x", "*").replace("X", "*")
    # porcentagem: 50% -> (50/100)
    expr = re.sub(r"(\d+(?:\.\d+)?)%", r"(\1/100)", expr)
    # multiplicação implícita: 2(3) e (2)(3) e (2)3
    expr = re.sub(r"(\d|\))\s*\(", r"\1*(", expr)
    expr = re.sub(r"\)\s*(\d)", r")*\1", expr)
    return expr


def _walk(node: ast.AST) -> Decimal:
    if isinstance(node, ast.Expression):
        return _walk(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return Decimal(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _walk(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left, right = _walk(node.left), _walk(node.right)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, (ast.Div, ast.Mod)):
            if right == 0:
                raise CalculatorError("Não é possível dividir por zero.")
            return left / right if isinstance(op, ast.Div) else left % right
        if isinstance(op, ast.Pow):
            if abs(right) > MAX_EXPONENT:
                raise CalculatorError("Expoente muito grande.")
            if right != right.to_integral_value() and left < 0:
                raise CalculatorError("Raiz de número negativo não é suportada.")
            return left ** right
    raise CalculatorError("A expressão contém elementos não permitidos.")


def evaluate(expression: str) -> Decimal:
    """Avalia a expressão e retorna um ``Decimal``. Levanta ``CalculatorError``."""
    if not expression or not expression.strip():
        raise CalculatorError("Digite uma expressão.")
    if len(expression) > MAX_LENGTH:
        raise CalculatorError("Expressão muito longa.")
    expr = normalize(expression)
    if re.search(r"\d\.\d*\.", expr):
        raise CalculatorError("Número com mais de uma vírgula decimal.")
    if not re.fullmatch(r"[\d.+\-*/%() ]+", expr):
        raise CalculatorError("Use apenas números e operadores (+ − × ÷ ^ %).")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        if expr.count("(") != expr.count(")"):
            raise CalculatorError("Parênteses não estão balanceados.") from None
        raise CalculatorError("Expressão incompleta ou inválida.") from None
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.Emax = 999999
        ctx.Emin = -999999
        try:
            result = _walk(tree)
        except (DivisionByZero, ZeroDivisionError):
            raise CalculatorError("Não é possível dividir por zero.") from None
        except (Overflow, OverflowError):
            raise CalculatorError("Resultado grande demais para exibir.") from None
        except InvalidOperation:
            raise CalculatorError("Operação matemática inválida.") from None
        except RecursionError:
            raise CalculatorError("Expressão complexa demais.") from None
        return +result  # aplica a precisão do contexto


def format_result(value: Decimal) -> str:
    """Resultado para exibição (pt-BR, sem separador de milhar, para poder ser reutilizado)."""
    return number_br(value, max_decimals=10, grouping=False)


def try_preview(expression: str) -> str | None:
    """Resultado parcial silencioso, usado como prévia enquanto o usuário digita."""
    try:
        return format_result(evaluate(expression))
    except CalculatorError:
        return None
