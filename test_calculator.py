from decimal import Decimal

import pytest

from app.services.calculator_engine import CalculatorError, evaluate, format_result


@pytest.mark.parametrize("expr,expected", [
    ("12 + 8", "20"), ("7 × 6", "42"), ("100 ÷ 4", "25"), ("0,1 + 0,2", "0,3"),
    ("2 × (3 + 4)", "14"), ("10 − 15", "-5"), ("2^10", "1024"), ("200 × 10%", "20"),
    ("50%", "0,5"), ("1 ÷ 3", "0,3333333333"), ("-(-3)", "3"), ("2(3+1)", "8"), ("1.5 + 1,5", "3"),
])
def test_valid(expr, expected):
    assert format_result(evaluate(expr)) == expected


@pytest.mark.parametrize("expr,msg", [
    ("1 ÷ 0", "dividir por zero"), ("2 +", "inválida"), ("(1 + 2", "Parênteses"),
    ("__import__('os')", "apenas números"), ("", "Digite"), ("2^100000", "Expoente"),
    ("1,2,3", "vírgula"),
])
def test_invalid(expr, msg):
    with pytest.raises(CalculatorError) as exc:
        evaluate(expr)
    assert msg in str(exc.value)


def test_large_numbers():
    assert evaluate("10^30") == Decimal(10) ** 30
