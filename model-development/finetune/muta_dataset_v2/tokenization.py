"""Exact Qwen chat-template token accounting for release builds."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

TOKENIZER_ID = "Qwen/Qwen2.5-1.5B-Instruct"
TOKENIZER_REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
CHAT_TEMPLATE_SHA256 = "cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f"
DEFAULT_MAX_SEQUENCE_TOKENS = 1024


class TokenLimitError(ValueError):
    """Raised when a rendered training example would be truncated."""


class QwenTokenCounter:
    def __init__(
        self,
        *,
        tokenizer_id: str = TOKENIZER_ID,
        revision: str = TOKENIZER_REVISION,
        max_sequence_tokens: int = DEFAULT_MAX_SEQUENCE_TOKENS,
    ) -> None:
        try:
            from transformers import AutoTokenizer
        except ImportError as exc:  # pragma: no cover - exercised in build environments
            raise RuntimeError(
                "exact token accounting requires the pinned transformers build dependency"
            ) from exc
        self.tokenizer_id = tokenizer_id
        self.revision = revision
        self.max_sequence_tokens = max_sequence_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(
            tokenizer_id,
            revision=revision,
            trust_remote_code=False,
        )
        template = self.tokenizer.chat_template
        if not template:
            raise RuntimeError(f"{tokenizer_id}@{revision} does not expose a chat template")
        self.chat_template_sha256 = hashlib.sha256(template.encode("utf-8")).hexdigest()
        if (
            tokenizer_id == TOKENIZER_ID
            and revision == TOKENIZER_REVISION
            and self.chat_template_sha256 != CHAT_TEMPLATE_SHA256
        ):
            raise RuntimeError(
                "pinned Qwen chat template hash changed: "
                f"expected {CHAT_TEMPLATE_SHA256}, observed {self.chat_template_sha256}"
            )

    def count(self, messages: list[dict[str, str]]) -> int:
        token_ids = self.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=False,
        )
        if isinstance(token_ids, Mapping):
            token_ids = token_ids["input_ids"]
        if token_ids and isinstance(token_ids[0], list):
            if len(token_ids) != 1:
                raise ValueError("expected one tokenized example")
            token_ids = token_ids[0]
        return len(token_ids)

    def annotate(self, record: dict[str, Any]) -> None:
        sequence_tokens = self.count(record["messages"])
        if sequence_tokens > self.max_sequence_tokens:
            raise TokenLimitError(
                f"record {record.get('id')} renders to {sequence_tokens} tokens; "
                f"limit is {self.max_sequence_tokens}"
            )
        record["tokenization"] = {
            "tokenizer_id": self.tokenizer_id,
            "tokenizer_revision": self.revision,
            "chat_template_sha256": self.chat_template_sha256,
            "sequence_tokens": sequence_tokens,
            "max_sequence_tokens": self.max_sequence_tokens,
            "within_limit": True,
        }

    def validate(self, record: dict[str, Any]) -> bool:
        metadata = record.get("tokenization") or {}
        return metadata == {
            "tokenizer_id": self.tokenizer_id,
            "tokenizer_revision": self.revision,
            "chat_template_sha256": self.chat_template_sha256,
            "sequence_tokens": self.count(record["messages"]),
            "max_sequence_tokens": self.max_sequence_tokens,
            "within_limit": True,
        }
