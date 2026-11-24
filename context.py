"""Contexto compartilhado entre os módulos visuais e classe base das telas."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import flet as ft

from app import config
from app.database.connection import DatabaseError
from app.services.container import Services
from app.ui.components.feedback import Notifier
from app.utils.validators import ValidationError


@dataclass
class AppContext:
    page: ft.Page
    services: Services
    notify: Notifier
    file_picker: ft.FilePicker
    layout: str = "desktop"  # 'mobile' | 'tablet' | 'desktop'
    navigate: Callable[[str], None] = field(default=lambda key: None)

    @property
    def is_mobile(self) -> bool:
        return self.layout == "mobile"

    @property
    def is_desktop(self) -> bool:
        return self.layout == "desktop"

    @property
    def width(self) -> float:
        return float(self.page.width or 1200)

    @staticmethod
    def layout_for(width: float) -> str:
        if width < config.BREAKPOINT_MOBILE:
            return "mobile"
        if width < config.BREAKPOINT_DESKTOP:
            return "tablet"
        return "desktop"

    def run_safely(self, action: Callable[[], None], success: Optional[str] = None,
                   then: Optional[Callable[[], None]] = None) -> bool:
        """Executa uma ação de negócio tratando erros de validação e de banco.

        ``then`` roda após o sucesso e antes da notificação (ex.: fechar o diálogo)."""
        try:
            action()
        except ValidationError as exc:
            self.notify.error(str(exc))
            return False
        except DatabaseError as exc:
            self.notify.error(str(exc))
            return False
        except Exception as exc:  # erro inesperado: informa sem encerrar o app
            self.notify.error(f"Erro inesperado: {exc}")
            return False
        if then:
            then()
        if success:
            self.notify.success(success)
        return True


class ModuleView:
    """Base de cada módulo. O estado fica na instância; ``build`` gera a interface
    a partir dele, permitindo reconstruir a tela quando o layout muda."""

    key = ""

    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.root = ft.Container(expand=True, key=self.key)

    @property
    def page(self) -> ft.Page:
        return self.ctx.page

    def build(self) -> ft.Control:  # pragma: no cover - abstrato
        raise NotImplementedError

    def mount(self) -> ft.Container:
        """Cria um novo contêiner raiz (usado em troca de módulo ou de layout)."""
        self.root = ft.Container(content=self.build(), expand=True, key=self.key)
        return self.root

    def refresh(self) -> None:
        self.root.content = self.build()
        try:
            self.root.update()
        except Exception:
            pass  # tela ainda não está na página

    def on_show(self) -> None:
        """Chamado quando o módulo se torna visível."""

    def on_key(self, e: ft.KeyboardEvent) -> None:
        """Atalhos de teclado (opcional)."""
