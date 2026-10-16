"""Decode only supported raster uploads and pass a fresh pixel-only JPEG to downstream readers."""

import base64
import io
import warnings
from functools import cache
from pathlib import Path

import yaml
from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field


class PhotoLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    max_bytes: int = Field(2000000, ge=1)
    max_pixels: int = Field(16000000, ge=1)
    max_side: int = Field(2048, ge=1)


@cache
def limits() -> PhotoLimits:
    path = Path(__file__).resolve().parents[3] / "config" / "security.yaml"
    return PhotoLimits.model_validate(yaml.safe_load(path.read_text(encoding="utf-8"))["photo"])


def sanitize_photo(value: str) -> bytes:
    cfg = limits()
    if len(value) > ((cfg.max_bytes + 2) // 3) * 4 + 64:
        raise ValueError("photo too large")
    header, raw = value.split(",", 1)
    formats = {"data:image/jpeg;base64": "JPEG", "data:image/png;base64": "PNG", "data:image/webp;base64": "WEBP"}
    if header not in formats:
        raise ValueError("unsupported photo type")
    data = base64.b64decode(raw, validate=True)
    if not 0 < len(data) <= cfg.max_bytes:
        raise ValueError("photo too large")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            if image.format != formats[header] or image.width * image.height > cfg.max_pixels \
                    or getattr(image, "n_frames", 1) != 1:
                raise ValueError("unsupported photo")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            rgb = ImageOps.exif_transpose(image).convert("RGB")
            rgb.thumbnail((cfg.max_side, cfg.max_side))
            clean = Image.new("RGB", rgb.size)
            clean.paste(rgb)
            out = io.BytesIO()
            clean.save(out, format="JPEG", quality=90)
            return out.getvalue()
