"""Visual Office Manager — ponto de entrada.

Execução:
    python main.py            # janela desktop
    flet run main.py          # desktop com recarga automática
    flet run --web main.py    # navegador
    python main.py --web      # navegador (porta 8550)
"""
from __future__ import annotations

import logging
import sys

import flet as ft

from app import config
from app.services.container import build_services
from app.services.image_service import render_app_icon
from app.services.demo_data import seed
from app.ui.shell import AppShell, configure_page
from app.utils.runtime import IS_BROWSER

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("visual_office")


def ensure_assets() -> None:
    """Gera o ícone com Pillow na primeira execução (sem depender de arquivo externo)."""
    icon = config.ASSETS_DIR / "icons" / "icon.png"
    if not icon.exists():
        icon.parent.mkdir(parents=True, exist_ok=True)
        render_app_icon(512).save(icon)


def main(page: ft.Page) -> None:
    configure_page(page)
    try:
        services = build_services()
    except Exception as exc:  # falha ao abrir o banco: mostra a causa em vez de fechar
        log.exception("Falha ao iniciar")
        page.add(ft.Text(f"Não foi possível iniciar o aplicativo: {exc}", color="#8C2434"))
        return
    if IS_BROWSER:  # versão web de demonstração: banco em memória, começa com dados de exemplo
        try:
            seed(services)
        except Exception:
            log.exception("Falha ao inserir dados de demonstração")
    shell = AppShell(page, services)
    shell.mount()


if __name__ == "__main__" and IS_BROWSER:
    ft.run(main, assets_dir="assets")
elif __name__ == "__main__":
    ensure_assets()
    web = "--web" in sys.argv
    ft.run(
        main,
        assets_dir=str(config.ASSETS_DIR),
        view=ft.AppView.WEB_BROWSER if web else ft.AppView.FLET_APP,
        port=8550 if web else 0,
        no_cdn=True,
    )
