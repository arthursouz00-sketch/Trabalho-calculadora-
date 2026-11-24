"""Gera a versão web estática (Python rodando no navegador via Pyodide).

    python tools/build_web.py            # resultado em dist_web/

O resultado é uma pasta de arquivos estáticos que pode ser hospedada em
qualquer servidor estático (Netlify, GitHub Pages, Vercel...) ou testada
localmente com:  python -m http.server 8000 --directory dist_web

Além do ``flet publish``, o script:
* torna todos os caminhos relativos (funciona em subpastas, ex. GitHub Pages);
* empacota TODAS as dependências (flet, Pillow, msgpack...) junto do site,
  sem baixar nada de PyPI/CDN no navegador;
* remove o service worker e variantes de renderização não usadas.
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist_web"
FLET_VERSION = "1.1.3"
PURE_WHEELS = [f"flet=={FLET_VERSION}", "repath==0.9.0"]
PYODIDE_PACKAGES = ["pillow", "msgpack", "six"]  # pacotes compilados p/ WebAssembly
LOADING = """
  <div id="loading" role="status" aria-live="polite">
    <img src="icons/icon.png" alt="">
    <h1>Visual Office Manager</h1>
    <div class="bar"><i></i></div>
    <p>Carregando o aplicativo. O Python roda direto no seu navegador, por isso a primeira abertura leva alguns segundos.</p>
  </div>
  <style>
    html,body{height:100%;margin:0;background:#F4F6F5}
    #loading{position:fixed;inset:0;display:flex;flex-direction:column;gap:18px;align-items:center;justify-content:center;
      background:#F4F6F5;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;text-align:center;padding:0 16px}
    #loading img{width:88px;height:88px;border-radius:22px;box-shadow:0 8px 24px rgba(18,51,38,.25)}
    #loading h1{margin:0;font-size:20px;color:#1F4D3A}
    #loading p{margin:0;font-size:13px;color:#66716B;max-width:32ch}
    #loading .bar{width:160px;height:4px;border-radius:4px;background:#E2E7E4;overflow:hidden}
    #loading .bar i{display:block;height:100%;width:40%;background:#1F4D3A;border-radius:4px;animation:s 1.2s ease-in-out infinite}
    @keyframes s{0%{transform:translateX(-100%)}100%{transform:translateX(250%)}}
  </style>
"""


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def publish(stage: Path) -> None:
    for item in ("main.py", "app", "assets", "pyproject.toml"):
        src = ROOT / item
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, stage / item)
    for cache in stage.rglob("__pycache__"):
        shutil.rmtree(cache)
    if DIST.exists():
        shutil.rmtree(DIST)
    run(["flet", "publish", "main.py", "--distpath", str(DIST), "-a", "assets", "--no-cdn",
         "--app-name", "Visual Office Manager", "--app-short-name", "Visual Office",
         "--app-description", "Calendário, calculadora, pessoas e finanças",
         "--route-url-strategy", "hash", "--pwa-theme-color", "#1F4D3A",
         "--pwa-background-color", "#F4F6F5"], cwd=stage)


def patch_paths() -> None:
    index = DIST / "index.html"
    s = index.read_text(encoding="utf-8")
    repl = {
        '<base href="/">': '<base href="./">',
        'flet.pyodideUrl="pyodide/pyodide.mjs";': 'flet.pyodideUrl=new URL("pyodide/pyodide.mjs", document.baseURI).href;',
        'flet.appPackageUrl = "app.tar.gz";': 'flet.appPackageUrl = new URL("app.tar.gz", document.baseURI).href;',
        'flet.canvasKitBaseUrl="/canvaskit/";': 'flet.canvasKitBaseUrl="canvaskit/";',
        'flet.entrypointBaseUrl="/";': 'flet.entrypointBaseUrl="./";',
        'flet.assetBase="/";': 'flet.assetBase="./";',
    }
    for old, new in repl.items():
        if old not in s:
            raise SystemExit(f"index.html mudou de formato; trecho não encontrado: {old}")
        s = s.replace(old, new)
    start, end = s.index('<div id="loading"'), s.index("</div>", s.index('<div id="loading"')) + 6
    s = s[:start] + LOADING + s[end:]
    index.write_text(s, encoding="utf-8")

    boot = DIST / "flutter_bootstrap.js"
    b = boot.read_text(encoding="utf-8")
    i = b.rfind("serviceWorkerSettings:")  # a última ocorrência é a configuração (as anteriores são código do loader)
    if i != -1:  # service worker não é necessário e falha em alguns hosts
        j = b.index("},", i) + 2
        b = b[:i] + b[j:]
        boot.write_text(b, encoding="utf-8")


def bundle_dependencies() -> None:
    wheels = DIST / "wheels"
    wheels.mkdir(exist_ok=True)
    run([sys.executable, "-m", "pip", "download", "--no-deps", "-q", "-d", str(wheels), *PURE_WHEELS])

    pyodide_dir = DIST / "pyodide"
    lock = json.loads((pyodide_dir / "pyodide-lock.json").read_text())
    version = json.loads((pyodide_dir / "package.json").read_text())["version"]
    needed = {lock["packages"][p]["file_name"] for p in PYODIDE_PACKAGES}
    missing = {n for n in needed if not (pyodide_dir / n).exists()}
    if missing:
        url = f"https://github.com/pyodide/pyodide/releases/download/{version}/pyodide-{version}.tar.bz2"
        print(f"Baixando pacotes Pyodide de {url} (pode demorar)...")
        with urllib.request.urlopen(url) as resp, tarfile.open(fileobj=resp, mode="r|bz2") as tar:
            for member in tar:
                name = Path(member.name).name
                if name in missing:
                    (pyodide_dir / name).write_bytes(tar.extractfile(member).read())
                    missing.discard(name)
                    if not missing:
                        break
    if missing:
        raise SystemExit(f"Pacotes Pyodide não encontrados: {missing}")

    # requirements.txt do pacote do app: só arquivos locais
    app_tar = DIST / "app.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(app_tar) as tar:
            tar.extractall(tmp, filter="data")
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").unlink(missing_ok=True)
        reqs = [f"wheels/{w.name}" for w in sorted(wheels.glob("*.whl"))] + PYODIDE_PACKAGES
        (tmp_path / "requirements.txt").write_text("\n".join(reqs) + "\n")
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for f in sorted(tmp_path.rglob("*")):
                tar.add(f, arcname=f.relative_to(tmp_path).as_posix(), recursive=False)
        app_tar.write_bytes(buf.getvalue())


def prune() -> None:
    for pattern in ("canvaskit/skwasm*", "canvaskit/wimp*", "canvaskit/webparagraph", "canvaskit/**/*.symbols",
                    "flutter.js.map", "main.dart.wasm", "main.dart.mjs", "flutter_service_worker.js",
                    "pyodide/python", "pyodide/python.bat", "pyodide/python.exe", "pyodide/python_cli_entry.mjs",
                    "pyodide/*.d.ts", "assets/packages/flutter_local_notifications_web", "assets/packages/media_kit",
                    "assets/packages/record_web", "assets/packages/wakelock_plus", "assets/packages/flutter_map"):
        for path in DIST.glob(pattern):
            shutil.rmtree(path) if path.is_dir() else path.unlink()


def main() -> None:
    with tempfile.TemporaryDirectory() as stage:
        publish(Path(stage))
    patch_paths()
    bundle_dependencies()
    prune()
    size = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print(f"\nPronto: {DIST} ({size / 1e6:.0f} MB)")
    print("Teste local:  python -m http.server 8000 --directory dist_web   ->  http://localhost:8000")


if __name__ == "__main__":
    main()
