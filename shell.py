"""Estrutura principal: cabeçalho, navegação adaptativa e área de conteúdo animada."""
from __future__ import annotations

import flet as ft

from app import config
from app.services.container import Services
from app.ui import theme as t
from app.ui.components.feedback import Notifier
from app.ui.components.header import Header
from app.ui.components.navigation import NAV_ITEMS, Sidebar, bottom_navigation
from app.ui.context import AppContext, ModuleView


class AppShell:
    def __init__(self, page: ft.Page, services: Services):
        self.page = page
        self.services = services
        file_picker = ft.FilePicker()  # serviço registrado automaticamente na página
        self.ctx = AppContext(page=page, services=services, notify=Notifier(page),
                              file_picker=file_picker, navigate=self.navigate)
        self.ctx.layout = AppContext.layout_for(page.width or 1200)

        # Importação tardia evita dependência circular entre módulos e shell
        from app.modules.calculator.view import CalculatorView
        from app.modules.calendar.view import CalendarView
        from app.modules.finance.view import FinanceView
        from app.modules.people.view import PeopleView

        self.views: dict[str, ModuleView] = {
            "calendar": CalendarView(self.ctx),
            "calculator": CalculatorView(self.ctx),
            "people": PeopleView(self.ctx),
            "finance": FinanceView(self.ctx),
        }
        saved = services.settings.get("last_module", "calendar")
        self.current = saved if saved in self.views else "calendar"
        self.snow_enabled = services.settings.get("snow", "1") == "1"
        self.header: Header | None = None
        self.sidebar: Sidebar | None = None
        self.switcher = ft.AnimatedSwitcher(
            content=ft.Container(),
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=ft.Duration(milliseconds=260),
            reverse_duration=ft.Duration(milliseconds=120),
            switch_in_curve=ft.AnimationCurve.EASE_OUT_CUBIC,
            switch_out_curve=ft.AnimationCurve.EASE_IN,
            expand=True,
        )

        page.on_resize = self._on_resize
        page.on_keyboard_event = self._on_key

        # WhatsApp real: reativa o recebimento e escuta novas mensagens
        self._live_error = services.live.auto_start()
        services.whatsapp.add_listener(self._on_whatsapp_event)
        page.on_close = self._on_close
        page.on_disconnect = self._on_close

    # ---------- montagem ----------
    def mount(self) -> None:
        self._build_layout()
        self.views[self.current].on_show()
        if self._live_error:
            self.ctx.notify.error(f"WhatsApp: {self._live_error}")

    # ---------- WhatsApp em tempo real ----------
    def _on_whatsapp_event(self, summary: str) -> None:
        """Chamado pela thread do webhook; repassa ao loop da interface."""
        try:
            self.page.run_task(self._apply_whatsapp_event, summary)
        except Exception:
            pass

    async def _apply_whatsapp_event(self, summary: str) -> None:
        self.ctx.notify.success(f"WhatsApp: {summary}")
        view = self.views.get(self.current)
        if self.current == "finance" and hasattr(view, "live_refresh"):
            view.live_refresh()

    def _on_close(self, _=None) -> None:
        self.services.whatsapp.remove_listener(self._on_whatsapp_event)
        if self.header:
            self.header.stop()

    def _content_area(self) -> ft.Container:
        pad = 12 if self.ctx.is_mobile else (18 if self.ctx.layout == "tablet" else 26)
        self.switcher.content = self.views[self.current].mount()
        return ft.Container(self.switcher, padding=ft.Padding.only(left=pad, right=pad, top=pad, bottom=0 if self.ctx.is_mobile else pad),
                            expand=True)

    def _build_layout(self) -> None:
        page = self.page
        if self.header:
            self.header.stop()
        self.header = Header(page, compact=self.ctx.is_mobile, snow_enabled=self.snow_enabled,
                             on_toggle_snow=self._save_snow)
        content = self._content_area()
        if self.ctx.is_mobile:
            self.sidebar = None
            page.navigation_bar = bottom_navigation(self.current, self.navigate)
            body: ft.Control = content
        else:
            page.navigation_bar = None
            self.sidebar = Sidebar(self.current, self.navigate, compact=self.ctx.layout == "tablet")
            body = ft.Row([self.sidebar.control, content], spacing=0, expand=True,
                          vertical_alignment=ft.CrossAxisAlignment.STRETCH)
        page.controls = [ft.Column([self.header.control, body], spacing=0, expand=True)]
        page.update()
        self.header.start()

    # ---------- eventos ----------
    def navigate(self, key: str) -> None:
        if key not in self.views:
            return
        if key == self.current:
            self.views[key].on_show()
            return
        self.current = key
        self.services.settings.set("last_module", key)
        self.switcher.content = self.views[key].mount()
        if self.sidebar:
            self.sidebar.set_selected(key)
        if self.page.navigation_bar is not None:
            self.page.navigation_bar.selected_index = [i.key for i in NAV_ITEMS].index(key)
        self.page.update()
        self.views[key].on_show()

    def _on_resize(self, e) -> None:
        layout = AppContext.layout_for(self.page.width or 1200)
        if layout != self.ctx.layout:
            self.ctx.layout = layout
            self._build_layout()

    def _on_key(self, e: ft.KeyboardEvent) -> None:
        self.views[self.current].on_key(e)

    def _save_snow(self, enabled: bool) -> None:
        self.snow_enabled = enabled
        self.services.settings.set("snow", "1" if enabled else "0")


def configure_page(page: ft.Page) -> None:
    page.title = config.APP_NAME
    page.fonts = {t.FONT: "fonts/Inter.ttf"}
    page.theme = t.build_theme()
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = t.ICE
    page.padding = 0
    page.spacing = 0
    page.locale_configuration = ft.LocaleConfiguration(
        supported_locales=[ft.Locale("pt", "BR"), ft.Locale("en", "US")],
        current_locale=ft.Locale("pt", "BR"),
    )
    try:
        page.window.min_width = 380
        page.window.min_height = 620
        if not page.web and page.platform not in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
            page.window.width = 1320
            page.window.height = 860
    except Exception:
        pass
