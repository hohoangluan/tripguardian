"""The Embedder role: an image or a text -> a unit vector. Deterministic for one model; the model ids live in
config/index.yaml, the weights in the repo cache (.cache/hf). Offline for the corpus, online for the user's words or
photo; nothing it embeds is stored by this module."""

from __future__ import annotations

import io
import os
from functools import cached_property
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config" / "index.yaml"


def config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _hf_env() -> None:
    os.environ.setdefault("HF_HOME", str(ROOT / ".cache" / "hf"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")


def _unit(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-8)


class Embedder:
    """image(), image_text(): SigLIP2, one space for photos and short descriptions. text(): bge-m3, for spans."""

    def __init__(self, device: str | None = None, cfg: dict | None = None):
        self.cfg = (cfg or config())["embedder"]
        self.device = device or self.cfg["online_device"]
        _hf_env()

    @property
    def image_model_id(self) -> str:
        return self.cfg["image_model"]

    @property
    def text_model_id(self) -> str:
        return self.cfg["text_model"]

    @cached_property
    def _torch(self):
        import torch
        return torch

    def _dtype(self):
        return self._torch.float16 if self.device.startswith("cuda") else self._torch.float32

    @cached_property
    def _siglip(self):
        from transformers import AutoModel, AutoProcessor
        m = AutoModel.from_pretrained(self.image_model_id, dtype=self._dtype()).to(self.device).eval()
        return m, AutoProcessor.from_pretrained(self.image_model_id)

    @cached_property
    def _bge(self):
        from transformers import AutoModel, AutoTokenizer
        m = AutoModel.from_pretrained(self.text_model_id, dtype=self._dtype()).to(self.device).eval()
        return m, AutoTokenizer.from_pretrained(self.text_model_id)

    @staticmethod
    def _out(v):
        return v.pooler_output if hasattr(v, "pooler_output") else v

    def image(self, images: list) -> np.ndarray:
        """images: PIL images or encoded bytes -> (n, d) unit float32."""
        from PIL import Image
        pil = [Image.open(io.BytesIO(x)).convert("RGB") if isinstance(x, (bytes, bytearray)) else x.convert("RGB")
               for x in images]
        m, p = self._siglip
        with self._torch.no_grad():
            px = p(images=pil, return_tensors="pt")["pixel_values"].to(self.device, self._dtype())
            return _unit(self._out(m.get_image_features(pixel_values=px)).float().cpu().numpy())

    def image_text(self, texts: list[str]) -> np.ndarray:
        """Short descriptions in the photo space ("đèn vàng, ghế gỗ") -> (n, d) unit float32."""
        m, p = self._siglip
        with self._torch.no_grad():
            t = p(text=[x.lower() for x in texts], padding="max_length", max_length=self.cfg["image_text_len"],
                  truncation=True, return_tensors="pt").to(self.device)
            return _unit(self._out(m.get_text_features(**t)).float().cpu().numpy())

    def text(self, texts: list[str]) -> np.ndarray:
        """bge-m3 dense vectors (CLS, normalised) -> (n, d) unit float32."""
        m, tok = self._bge
        with self._torch.no_grad():
            t = tok(texts, padding=True, truncation=True, max_length=256, return_tensors="pt").to(self.device)
            return _unit(m(**t).last_hidden_state[:, 0].float().cpu().numpy())
