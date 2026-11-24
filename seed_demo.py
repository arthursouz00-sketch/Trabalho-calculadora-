"""Popula o banco com dados de demonstração para a apresentação.

Só insere dados se o banco estiver vazio, para não duplicar registros.

    python tools/seed_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.container import build_services  # noqa: E402
from app.services.demo_data import seed  # noqa: E402

if __name__ == "__main__":
    if seed(build_services()):
        print("Dados de demonstração inseridos com sucesso.")
    else:
        print("O banco já possui dados; nada foi inserido.")
