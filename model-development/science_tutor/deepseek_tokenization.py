"""Native closed-message masking for DeepSeek-R1-Distill-Qwen.

The publisher's template adds a ``<think>`` generation prefix when a
generation prompt is requested, so the Qwen ChatML prefix-difference mask is
not valid here.  This profile trains on the exact closed native rendering of
each conversation.  For each assistant turn, an empty assistant message gives
the native header plus its final EOS; removing exactly that EOS yields the
causal prefix.  Prefix identity is checked against the full closed rendering
before any labels are admitted.
"""

from __future__ import annotations

from collections.abc import Mapping

try:
    from .tokenization import TokenizationError, digest, validate_messages
except ImportError:  # direct invocation on a training host
    from tokenization import TokenizationError, digest, validate_messages


def _ids(tokenizer, messages):
    value = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=False,
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


def _control_strings(tokenizer):
    # DeepSeek's think markers are native template controls but are not both
    # exposed by all_special_tokens.  Reject them explicitly rather than
    # allowing a row to alter the template's reasoning state.
    values = set(getattr(tokenizer, "all_special_tokens", ()))
    values.update({"<think>", "</think>"})
    return {value for value in values if value}


def tokenize_messages(messages, *, tokenizer, max_length=4096):
    """Tokenize a DeepSeek conversation with exact direct-answer supervision."""

    validate_messages(messages)
    if messages[0]["role"] == "system":
        raise TokenizationError("DeepSeek native profile rejects system messages")
    if type(max_length) is not int or max_length < 1:
        raise TokenizationError("max_length must be a positive integer")
    controls = _control_strings(tokenizer)
    for message in messages:
        if any(control in message["content"] for control in controls):
            raise TokenizationError("literal DeepSeek template control token inside message content")

    full = _ids(tokenizer, messages)
    if len(full) > max_length:
        raise TokenizationError(
            f"whole conversation has {len(full)} tokens > {max_length}; no truncation"
        )
    eos = getattr(tokenizer, "eos_token_id", None)
    if eos is None:
        raise TokenizationError("tokenizer lacks an explicit EOS token")
    labels = [-100] * len(full)
    spans = []
    for index, message in enumerate(messages):
        if message["role"] != "assistant":
            continue
        empty = messages[:index] + [{"role": "assistant", "content": ""}]
        empty_ids = _ids(tokenizer, empty)
        if not empty_ids or empty_ids[-1] != eos:
            raise TokenizationError("native empty assistant does not close with tokenizer EOS")
        prefix = empty_ids[:-1]
        closed = _ids(tokenizer, messages[: index + 1])
        if full[: len(prefix)] != prefix or full[: len(closed)] != closed:
            raise TokenizationError("native closed rendering is not prefix-stable")
        start, stop = len(prefix), len(closed)
        if not 0 < start < stop <= len(full):
            raise TokenizationError("assistant has no causal target tokens")
        if any(value != -100 for value in labels[start:stop]):
            raise TokenizationError("overlapping assistant supervision spans")
        decoded = tokenizer.decode(full[start:stop], skip_special_tokens=False)
        if decoded != message["content"] + tokenizer.eos_token:
            raise TokenizationError("native assistant span is not exact content plus EOS")
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
        "trainable_tokens": sum(value != -100 for value in labels[1:]),
        "assistant_turns": len(spans),
        "messages_sha256": digest(messages),
        "input_ids_sha256": digest(full),
        "labels_sha256": digest(labels),
    }
