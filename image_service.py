"""Tratamento de fotografias com Pillow.

Fluxo: abrir -> corrigir orientação EXIF -> converter para RGB -> recorte
central quadrado (ajuste de proporção) -> redimensionar -> comprimir JPEG.
São gerados dois arquivos: foto padrão (512 px) e miniatura (128 px).
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

PHOTO_SIZE = 512
THUMB_SIZE = 128
JPEG_QUALITY = 82
MAX_INPUT_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "bmp", "gif", "heic"]


class ImageProcessingError(ValueError):
    pass


def _open(data: bytes) -> Image.Image:
    if not data:
        raise ImageProcessingError("Arquivo de imagem vazio.")
    if len(data) > MAX_INPUT_BYTES:
        raise ImageProcessingError("Imagem muito grande (máximo 25 MB).")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageProcessingError("Formato de imagem não reconhecido.") from exc
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        return background
    return img.convert("RGB")


def square_fit(img: Image.Image, size: int) -> Image.Image:
    """Recorta o centro em formato quadrado e redimensiona (proporção padronizada)."""
    return ImageOps.fit(img, (size, size), method=Image.Resampling.LANCZOS, centering=(0.5, 0.4))


def to_jpeg_bytes(img: Image.Image, quality: int = JPEG_QUALITY) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def process_photo(data: bytes) -> tuple[bytes, bytes]:
    """Retorna (foto_padronizada, miniatura) em JPEG."""
    img = _open(data)
    photo = square_fit(img, PHOTO_SIZE)
    thumb = square_fit(img, THUMB_SIZE)
    return to_jpeg_bytes(photo), to_jpeg_bytes(thumb, quality=78)


class PhotoStorage:
    """Grava e remove fotos processadas na pasta de dados."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes) -> tuple[str, str]:
        photo, thumb = process_photo(data)
        key = uuid.uuid4().hex
        photo_name, thumb_name = f"{key}.jpg", f"{key}_thumb.jpg"
        (self.folder / photo_name).write_bytes(photo)
        (self.folder / thumb_name).write_bytes(thumb)
        return photo_name, thumb_name

    def read(self, name: str | None) -> bytes | None:
        if not name:
            return None
        path = self.folder / Path(name).name  # impede caminhos fora da pasta
        try:
            return path.read_bytes()
        except OSError:
            return None

    def delete(self, *names: str | None) -> None:
        for name in names:
            if name:
                try:
                    (self.folder / Path(name).name).unlink(missing_ok=True)
                except OSError:
                    pass


def render_app_icon(size: int = 512) -> Image.Image:
    """Desenha o ícone do aplicativo (estrela dourada sobre verde-pinheiro)."""
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    radius = int(s * 0.23)
    # fundo com degradê vertical
    top, bottom = (36, 92, 66), (16, 51, 37)
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        gd.line([(0, y), (s, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)
    # estrela de cinco pontas
    import math
    cx, cy, r_out = s / 2, s * 0.47, s * 0.30
    r_in = r_out * 0.42
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    d.polygon(pts, fill=(222, 186, 106, 255))
    # faixa vinho na base (detalhe natalino discreto)
    d.rounded_rectangle((s * 0.30, s * 0.80, s * 0.70, s * 0.84), radius=int(s * 0.02), fill=(140, 36, 52, 255))
    return img.resize((size, size), Image.Resampling.LANCZOS)

