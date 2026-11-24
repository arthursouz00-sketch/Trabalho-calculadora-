"""Configurações globais da aplicação: nome, versão e caminhos de dados.

Os dados ficam fora da pasta de código para sobreviver a atualizações:
- ``VOM_DATA_DIR`` (variável de ambiente) tem prioridade, útil em testes;
- ``FLET_APP_STORAGE_DATA`` é definido pelo Flet em apps empacotados
  (Android/iOS/desktop gerados com ``flet build``);
- caso contrário, usa ``<projeto>/data``.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Visual Office Manager"
APP_SHORT_NAME = "Visual Office"
APP_VERSION = "2.0.0"
APP_EDITION = "Edição de Natal"

PROJECT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_DIR / "assets"


def data_dir() -> Path:
    """Retorna (e cria, se necessário) a pasta de dados persistentes."""
    base = (
        os.environ.get("VOM_DATA_DIR")
        or os.environ.get("FLET_APP_STORAGE_DATA")
        or str(PROJECT_DIR / "data")
    )
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "visual_office.db"


def photos_dir() -> Path:
    path = data_dir() / "photos"
    path.mkdir(parents=True, exist_ok=True)
    return path


# Pontos de quebra da interface responsiva (largura lógica em pixels)
BREAKPOINT_MOBILE = 640
BREAKPOINT_DESKTOP = 1024
