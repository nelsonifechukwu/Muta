"""Strict whole-conversation assistant-only supervision (no truncation or packing).

Assistant headers are context, not targets. Assistant content and the template's
closing turn tokens (including EOS) are targets, on *every* assistant turn.
Prefix equality is proved rather than guessed with a longest-common-prefix
fallback; incompatible templates fail closed. No text is reconstructed from a
last-turn prompt/completion projection.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


class TokenizationError(ValueError):
    """An invalid, unsafe, or overlength conversation must be quarantined."""


def canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_messages(messages):
    if not isinstance(messages, list) or not messages:
        raise TokenizationError("messages must be a nonempty list")
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise TokenizationError("messages require exactly role/content; no hidden tools/images")
        if not isinstance(message["content"], str) or not message["content"].strip():
            raise TokenizationError("message content must be nonempty text")
    start = int(messages[0]["role"] == "system")
    dialogue = messages[start:]
    if not dialogue or len(dialogue) % 2:
        raise TokenizationError("conversation must contain complete user/assistant pairs")
    for index, message in enumerate(dialogue):
        if message["role"] != ("user" if index % 2 == 0 else "assistant"):
            raise TokenizationError(
                "only an optional initial system then alternating user/assistant"
            )


def _ids(tokenizer, messages, *, generation=False):
    value = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=generation,
        truncation=False,
        padding=False,
    )
    if isinstance(value, Mapping):
        value = value["input_ids"]
    if hasattr(value, "tolist"):
        value = value.tolist()
    if value and isinstance(value[0], list):
        if len(value) != 1:
            raise TokenizationError("unexpected batched tokenizer result")
        value = value[0]
    if not isinstance(value, list) or any(type(x) is not int for x in value):
        raise TokenizationError("tokenizer must return a flat list of integer IDs")
    return value


def tokenize_messages(messages, *, tokenizer, max_length=4096):
    """Return exact tokens, masks, turn spans and counts, or fail without truncating.

    This public function is suitable for CPU-only dataset calibration before
    admission. It does not mutate messages or discard any conversation history.
    """
    validate_messages(messages)
    if type(max_length) is not int or max_length < 1:
        raise TokenizationError("max_length must be a positive integer")
    if not getattr(tokenizer, "chat_template", None):
        raise TokenizationError("an explicit frozen chat template is required")
    for message in messages:
        for special in getattr(tokenizer, "all_special_tokens", ()):
            if special and special in message["content"]:
                raise TokenizationError("literal tokenizer control token inside message content")
    full = _ids(tokenizer, messages)
    if len(full) > max_length:
        raise TokenizationError(
            f"whole conversation has {len(full)} tokens > {max_length}; no truncation"
        )
    labels = [-100] * len(full)
    spans = []
    for index, message in enumerate(messages):
        if message["role"] != "assistant":
            continue
        prefix = _ids(tokenizer, messages[:index], generation=True)
        closed = _ids(tokenizer, messages[: index + 1])
        if full[: len(prefix)] != prefix or full[: len(closed)] != closed:
            raise TokenizationError("chat template is not prefix-stable at an assistant boundary")
        start, stop = len(prefix), len(closed)
        if not 0 < start < stop <= len(full):
            raise TokenizationError("assistant has no causal target tokens")
        if getattr(tokenizer, "eos_token_id", None) not in full[start:stop]:
            raise TokenizationError("assistant closing turn does not include tokenizer EOS")
        if any(value != -100 for value in labels[start:stop]):
            raise TokenizationError("overlapping assistant supervision spans")
        labels[start:stop] = full[start:stop]
        spans.append({"message_index": index, "start": start, "stop": stop})
    if not spans or labels[0] != -100:
        raise TokenizationError("missing assistant supervision or invalid first-token target")
    return {
        "input_ids": full,
        "attention_mask": [1] * len(full),
        "labels": labels,
        "assistant_spans": spans,
        "sequence_tokens": len(full),
        "trainable_tokens": sum(x != -100 for x in labels[1:]),
        "assistant_turns": len(spans),
        "messages_sha256": digest(messages),
        "input_ids_sha256": digest(full),
        "labels_sha256": digest(labels),
    }
