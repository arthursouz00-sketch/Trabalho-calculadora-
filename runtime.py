"""Detecção do ambiente de execução.

Na versão web estática (``flet publish``) o Python roda dentro do navegador
(Pyodide/WebAssembly): não há threads nem servidores de rede locais.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any, Callable

IS_BROWSER = sys.platform == "emscripten"


async def run_blocking(fn: Callable[..., Any], *args: Any) -> Any:
    """Executa ``fn`` fora do loop da interface quando há threads; no navegador, chama direto."""
    if IS_BROWSER:
        return fn(*args)
    return await asyncio.to_thread(fn, *args)
