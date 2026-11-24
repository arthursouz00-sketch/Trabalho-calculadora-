"""Executa o app no modo navegador numa porta fixa (usado em testes visuais)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import flet as ft  # noqa: E402

from app import config  # noqa: E402
from main import ensure_assets, main  # noqa: E402

if __name__ == "__main__":
    ensure_assets()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8550
    ft.run(main, assets_dir=str(config.ASSETS_DIR), view=ft.AppView.WEB_BROWSER, port=port, no_cdn=True)
