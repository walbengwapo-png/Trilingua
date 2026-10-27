# -*- coding: utf-8 -*-
"""Local Hugging Face NLLB-200 provider used only for controlled benchmarks.

The provider deliberately lazy-loads its weights.  This keeps the normal
GPT-OSS service startup light and means NLLB is selected only by setting
``TRANSLATION_PROVIDER=nllb`` for an isolated evaluation server.
"""

from __future__ import annotations

import os
import threading
import time

from dto.requests import LANGUAGES
from dto.responses import TranslationResponse
from .base import TranslationProvider


class NLLBProvider(TranslationProvider):
    """Translate one source block locally with a pinned NLLB checkpoint."""

    def __init__(self, model_id: str = "", revision: str = "") -> None:
        self._model_id = model_id or os.environ.get(
            "NLLB_MODEL_ID", "facebook/nllb-200-distilled-600M"
        )
        self._revision = revision or os.environ.get(
            "NLLB_MODEL_REVISION", "f8d333a098d19b4fd9a8b18f94170487ad3f821d"
        )
        self._local_only = os.environ.get("NLLB_LOCAL_FILES_ONLY", "true").lower() in {
            "1", "true", "yes",
        }
        self._num_beams = max(1, int(os.environ.get("NLLB_NUM_BEAMS", "4")))
        self._max_input_tokens = max(64, int(os.environ.get("NLLB_MAX_INPUT_TOKENS", "400")))
        self._max_output_tokens = max(64, int(os.environ.get("NLLB_MAX_OUTPUT_TOKENS", "512")))
        self._model = None
        self._tokenizer = None
        self._load_lock = threading.Lock()
        self._generation_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "nllb"

    @property
    def model_name(self) -> str:
        return f"{self._model_id}@{self._revision}"

    @property
    def batch_limits(self) -> dict:
        # NLLB translates one block at a time.  A one-item limit prevents the
        # pipeline from asking a sequence-to-sequence model for JSON batches.
        return {"max_batch_chars": 4000, "max_batch_items": 1}

    @property
    def max_concurrency(self) -> int:
        # CPU inference is memory-intensive and deterministic serial execution
        # makes benchmark latency meaningful on the evaluation host.
        return 1

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return

        with self._load_lock:
            if self._model is not None and self._tokenizer is not None:
                return
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            configured_threads = os.environ.get("NLLB_TORCH_THREADS")
            if configured_threads:
                torch.set_num_threads(max(1, int(configured_threads)))

            kwargs = {
                "revision": self._revision,
                "local_files_only": self._local_only,
            }
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_id, **kwargs)
            self._model = AutoModelForSeq2SeqLM.from_pretrained(self._model_id, **kwargs)
            self._model.eval()

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        block_type: str = "paragraph",
        context_hint: str = "",
        document_type: str = "",
        response_format: str = "text",
    ) -> TranslationResponse:
        started = time.perf_counter()
        if source_lang not in LANGUAGES or target_lang not in LANGUAGES:
            return TranslationResponse(
                translated_text="",
                provider=self.name,
                model=self.model_name,
                success=False,
                error_message=f"Unsupported NLLB language pair: {source_lang} -> {target_lang}",
            )
        if not text.strip():
            return TranslationResponse(
                translated_text="",
                provider=self.name,
                model=self.model_name,
            )

        try:
            self._ensure_loaded()
            import torch

            # The fast tokenizer is backed by a Rust object and its language
            # state is mutable.  DocumentPipeline can schedule multiple
            # blocks even when the request-level concurrency is one, so the
            # entire tokenizer -> model -> decoder path must be serialized.
            # Locking only generate() caused intermittent "Already borrowed"
            # errors while another worker was encoding or decoding.
            with self._generation_lock, torch.inference_mode():
                # NLLB uses the source language token on its tokenizer and the
                # target language token as forced BOS during generation.
                self._tokenizer.src_lang = LANGUAGES[source_lang]
                encoded = self._tokenizer(
                    text,
                    return_tensors="pt",
                    truncation=True,
                    max_length=self._max_input_tokens,
                )
                # PDF extraction creates many short layout blocks. A fixed
                # high cap allows output longer than input while keeping a
                # predictable CPU-runtime envelope for malformed blocks.
                max_new_tokens = min(
                    self._max_output_tokens,
                    max(64, int(encoded["input_ids"].shape[1] * 1.75)),
                )
                forced_bos = self._tokenizer.convert_tokens_to_ids(LANGUAGES[target_lang])
                output = self._model.generate(
                    **encoded,
                    forced_bos_token_id=forced_bos,
                    max_new_tokens=max_new_tokens,
                    num_beams=self._num_beams,
                    early_stopping=True,
                )
                translated = self._tokenizer.batch_decode(
                    output, skip_special_tokens=True
                )[0].strip()
            if not translated:
                raise RuntimeError("NLLB generated an empty translation")

            return TranslationResponse(
                translated_text=translated,
                provider=self.name,
                model=self.model_name,
                token_usage={
                    "input": int(encoded["input_ids"].shape[1]),
                    "output": int(output.shape[1]),
                },
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as error:
            return TranslationResponse(
                translated_text="",
                provider=self.name,
                model=self.model_name,
                success=False,
                error_message=f"NLLB error: {error}",
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )

    def health(self) -> dict:
        return {
            "status": "ok",
            "provider": self.name,
            "model": self.model_name,
            "loaded": self._model is not None,
            "local_files_only": self._local_only,
        }

    def estimate_tokens(self, text: str) -> int:
        self._ensure_loaded()
        # TranslationPipeline estimates blocks from worker threads before
        # dispatching them.  The fast tokenizer cannot be borrowed by an
        # estimate thread while a generation thread is encoding/decoding.
        with self._generation_lock:
            return int(len(self._tokenizer.encode(text, add_special_tokens=True)))
