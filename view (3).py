"""Módulo 2 — Calculadora com expressões, prévia do resultado e histórico persistente."""
from __future__ import annotations

import flet as ft

from app.services.calculator_engine import CalculatorError, evaluate, format_result, try_preview
from app.ui import theme as t
from app.ui.components import widgets as w
from app.ui.components.feedback import confirm
from app.ui.context import ModuleView

OPERATORS = "+−×÷^"

# (rótulo, tipo, peso de largura)
KEYPAD = [
    [("C", "clear", 1), ("⌫", "back", 1), ("%", "op", 1), ("÷", "op", 1)],
    [("7", "num", 1), ("8", "num", 1), ("9", "num", 1), ("×", "op", 1)],
    [("4", "num", 1), ("5", "num", 1), ("6", "num", 1), ("−", "op", 1)],
    [("1", "num", 1), ("2", "num", 1), ("3", "num", 1), ("+", "op", 1)],
    [("(", "paren", 1), ("0", "num", 1), (",", "num", 1), (")", "paren", 1)],
    [("^", "op", 1), ("=", "equals", 3)],
]

KEY_MAP = {
    "Add": "+", "Numpad Add": "+", "+": "+", "=": None,
    "Minus": "−", "-": "−", "Numpad Subtract": "−",
    "*": "×", "Numpad Multiply": "×", "x": "×", "X": "×",
    "/": "÷", "Numpad Divide": "÷", "Slash": "÷",
    "(": "(", ")": ")", ".": ",", ",": ",", "Numpad Decimal": ",", "Period": ",", "Comma": ",",
    "%": "%", "^": "^",
}


class CalculatorView(ModuleView):
    key = "calculator"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.expression = ""
        self.last_expression = ""
        self.show_result = False
        self.error: str | None = None
        self.expr_text: ft.Text | None = None
        self.result_text: ft.Text | None = None
        self.error_text: ft.Text | None = None
        self.history_col: ft.Column | None = None
        self.display: ft.Container | None = None

    # ================= interface =================
    def build(self) -> ft.Control:
        mobile = self.ctx.is_mobile
        self.expr_text = ft.Text("", size=15 if mobile else 16, color=ft.Colors.with_opacity(0.7, t.SURFACE),
                                 text_align=ft.TextAlign.RIGHT, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)
        self.result_text = ft.Text("0", size=36 if mobile else 44, weight=ft.FontWeight.W_600, color=t.SURFACE,
                                   text_align=ft.TextAlign.RIGHT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                                   selectable=True)
        self.error_text = ft.Text("", size=13, color=t.GOLD, text_align=ft.TextAlign.RIGHT)
        self.display = ft.Container(
            ft.Column([self.expr_text, self.result_text, self.error_text], spacing=2,
                      horizontal_alignment=ft.CrossAxisAlignment.END, tight=True),
            padding=ft.Padding.only(left=20, right=20, top=18, bottom=12),
            border_radius=16,
            gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                                       colors=[t.PINE_DARK, t.PINE]),
            height=140 if mobile else 150,
            alignment=ft.Alignment.BOTTOM_RIGHT,
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        )
        self._render_display()
        key_height = 56 if mobile else 60
        keypad = ft.Column(
            [ft.Row([self._key(label, kind, weight, key_height) for label, kind, weight in row], spacing=10)
             for row in KEYPAD],
            spacing=10,
        )
        hint = ft.Text("Dica: use o teclado — Enter calcula, Esc limpa, Backspace apaga.", size=11,
                       color=t.TEXT_FAINT, visible=not mobile)
        calc_card = w.card(ft.Column([self.display, keypad, hint], spacing=16, tight=True),
                           padding=14 if mobile else 20, width=None if mobile else 420)
        history = self._history_card()
        if self.ctx.is_mobile:
            return ft.Column([calc_card, history], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
        return ft.Row([calc_card, history], spacing=22, vertical_alignment=ft.CrossAxisAlignment.START,
                      expand=True)

    def _key(self, label: str, kind: str, weight: int, height: int) -> ft.Container:
        styles = {
            "num": (t.SURFACE_ALT, t.TEXT, t.BORDER),
            "paren": (t.SURFACE_ALT, t.TEXT_MUTED, t.BORDER),
            "op": (t.PINE_SOFT, t.PINE, "#D2E2D8"),
            "clear": (t.WINE_SOFT, t.WINE, "#EDD3D8"),
            "back": (t.GOLD_SOFT, "#8A6A2B", "#EADFC4"),
            "equals": (t.PINE, t.SURFACE, t.PINE),
        }
        bg, fg, border = styles[kind]
        content: ft.Control = ft.Icon(ft.Icons.BACKSPACE_OUTLINED, color=fg, size=22) if kind == "back" else \
            ft.Text(label, size=22 if kind != "equals" else 24, weight=ft.FontWeight.W_600, color=fg)
        return ft.Container(
            content,
            expand=weight,
            height=height,
            bgcolor=bg,
            border=ft.Border.all(1, border),
            border_radius=14,
            alignment=ft.Alignment.CENTER,
            on_click=lambda _, l=label, k=kind: self._press(l, k),
            on_hover=self._hover,
            animate_scale=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
            shadow=t.shadow(1) if kind == "equals" else None,
            tooltip={"back": "Apagar", "clear": "Limpar", "^": "Potência"}.get(kind if kind != "op" else label),
        )

    def _hover(self, e: ft.ControlEvent) -> None:
        e.control.scale = 1.04 if e.data in (True, "true") else 1.0
        e.control.update()

    def _history_card(self) -> ft.Container:
        entries = self.ctx.services.calc_history.recent(50)
        self.history_col = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=not self.ctx.is_mobile,
                                     horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self._fill_history(entries)
        clear_btn = ft.TextButton("Limpar", icon=ft.Icons.DELETE_SWEEP_OUTLINED, on_click=self._ask_clear_history,
                                  style=ft.ButtonStyle(color=t.WINE), disabled=not entries)
        return w.card(
            ft.Column([w.section_header("Histórico", "Toque em um cálculo para reutilizar o resultado",
                                        [clear_btn]),
                       ft.Divider(height=1, color=t.BORDER), self.history_col],
                      spacing=10, expand=not self.ctx.is_mobile),
            padding=14 if self.ctx.is_mobile else 20,
            expand=not self.ctx.is_mobile,
        )

    def _fill_history(self, entries) -> None:
        if not entries:
            self.history_col.controls = [w.empty_state(ft.Icons.HISTORY_ROUNDED, "Sem cálculos ainda",
                                                       "Os resultados aparecem aqui e ficam salvos.", compact=True)]
            return
        self.history_col.controls = [
            ft.Container(
                ft.Column([
                    ft.Text(e.expression, size=13, color=t.TEXT_MUTED, text_align=ft.TextAlign.RIGHT),
                    ft.Text(f"= {e.result}", size=18, weight=ft.FontWeight.W_600, color=t.TEXT,
                            text_align=ft.TextAlign.RIGHT),
                ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.END, tight=True),
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                border_radius=12,
                bgcolor=t.SURFACE_ALT,
                border=ft.Border.all(1, t.BORDER),
                on_click=lambda _, r=e.result: self._reuse(r),
                tooltip="Usar este resultado",
            )
            for e in entries
        ]

    def _render_display(self) -> None:
        if self.result_text is None:
            return
        if self.show_result:
            self.expr_text.value = f"{self.last_expression} ="
            self.result_text.value = self.expression or "0"
        else:
            preview = try_preview(self.expression) if self.expression else None
            self.expr_text.value = f"= {preview}" if preview and preview != self.expression else ""
            self.result_text.value = self.expression or "0"
        self.result_text.size = self._fit_size(self.result_text.value)
        self.error_text.value = self.error or ""
        self.display.border = ft.Border.all(2, t.WINE) if self.error else None

    def _fit_size(self, text: str) -> int:
        base = 36 if self.ctx.is_mobile else 44
        n = len(text)
        if n <= 12:
            return base
        if n <= 18:
            return base - 10
        return base - 18

    def _update_display(self) -> None:
        self._render_display()
        try:
            self.display.update()
        except Exception:
            pass

    # ================= lógica dos botões =================
    def _press(self, label: str, kind: str) -> None:
        self.error = None
        if kind == "clear":
            self.expression, self.show_result = "", False
        elif kind == "back":
            if self.show_result:
                self.show_result = False
            self.expression = self.expression[:-1]
        elif kind == "equals":
            self._calculate()
            return
        else:
            self._append(label)
        self._update_display()

    def _append(self, token: str) -> None:
        if self.show_result:
            # depois do "=": operador continua a conta; número começa uma nova
            if token in OPERATORS or token == "%":
                self.show_result = False
            else:
                self.expression, self.show_result = "", False
        if len(self.expression) >= 120:
            self.error = "Limite de caracteres atingido."
            return
        last = self.expression[-1:] if self.expression else ""
        if token in OPERATORS:
            if not self.expression and token != "−":
                return  # expressão não pode começar com +, ×, ÷ ou ^
            if last in OPERATORS and not (token == "−" and last in "×÷^"):
                self.expression = self.expression[:-1]  # troca o operador
        if token == ",":
            # impede duas vírgulas no mesmo número
            number = ""
            for ch in reversed(self.expression):
                if ch.isdigit() or ch == ",":
                    number = ch + number
                else:
                    break
            if "," in number:
                return
            if not number:
                token = "0,"
        self.expression += token

    def _calculate(self) -> None:
        if not self.expression or self.show_result:
            return
        expr = self.expression
        try:
            value = evaluate(expr)
        except CalculatorError as exc:
            self.error = str(exc)
            self._update_display()
            return
        result = format_result(value)
        self.last_expression = expr
        self.expression = result
        self.show_result = True
        try:
            self.ctx.services.calc_history.add(expr, result)
        except Exception as exc:
            self.ctx.notify.error(f"Não foi possível salvar no histórico: {exc}")
        self.refresh()  # atualiza visor e histórico (botão "Limpar" passa a ficar ativo)

    def _reuse(self, result: str) -> None:
        if self.show_result or not self.expression:
            self.expression = result
        elif self.expression[-1] in OPERATORS or self.expression[-1] == "(":
            self.expression += result.lstrip("-") if result.startswith("-") and self.expression[-1] == "−" else result
        else:
            self.expression = result
        self.show_result = False
        self.error = None
        self._update_display()

    def _ask_clear_history(self, _) -> None:
        def clear():
            self.ctx.run_safely(self.ctx.services.calc_history.clear, "Histórico apagado.", then=self.refresh)
        confirm(self.page, "Apagar histórico?", "Todos os cálculos salvos serão removidos.", clear,
                confirm_text="Apagar")

    # ================= teclado =================
    def on_key(self, e: ft.KeyboardEvent) -> None:
        if getattr(self.page, "_dialogs", None) and any(d.open for d in self.page._dialogs.controls
                                                         if isinstance(d, ft.AlertDialog)):
            return  # não captura teclas enquanto há diálogo aberto
        key = e.key
        if key in ("Enter", "Numpad Enter", "=") and not e.shift:
            self._press("=", "equals")
        elif key == "Equal" and not e.shift:
            self._press("=", "equals")
        elif key == "Backspace":
            self._press("⌫", "back")
        elif key in ("Escape", "Delete"):
            self._press("C", "clear")
        elif e.shift and key in ("9", "Digit 9"):
            self._press("(", "paren")
        elif e.shift and key in ("0", "Digit 0"):
            self._press(")", "paren")
        elif e.shift and key in ("5", "Digit 5"):
            self._press("%", "op")
        elif e.shift and key in ("6", "Digit 6"):
            self._press("^", "op")
        elif e.shift and key in ("8", "Digit 8"):
            self._press("×", "op")
        elif e.shift and key in ("=", "Equal"):
            self._press("+", "op")
        elif len(key) == 1 and key.isdigit():
            self._press(key, "num")
        elif key.startswith("Numpad ") and key[-1].isdigit():
            self._press(key[-1], "num")
        elif key in KEY_MAP and KEY_MAP[key]:
            token = KEY_MAP[key]
            self._press(token, "num" if token == "," else ("paren" if token in "()" else "op"))
