"""Minimal GGUF metadata reader — enough to do the KV arithmetic (TDD T5, §5.2).

    python -m runtime.gguf models/core/*.gguf

Why not `gguf-py`: this reads a header, and the header format is four types of integer and a
length-prefixed string. Vendoring a dependency (plus numpy) into a 7 GiB budget to parse
that would be a poor trade, and the numbers this feeds — per-token KV bytes, hence slots ×
context — are too load-bearing to sit behind an unread abstraction.

Only the header is read; tensor data is never touched, so this costs a few KiB of IO on a
2.5 GiB file.
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

MAGIC = b"GGUF"

# GGUF value type ids → (struct format, size). Types 8 (string) and 9 (array) are special.
_SCALARS: dict[int, tuple[str, int]] = {
    0: ("<B", 1),   # uint8
    1: ("<b", 1),   # int8
    2: ("<H", 2),   # uint16
    3: ("<h", 2),   # int16
    4: ("<I", 4),   # uint32
    5: ("<i", 4),   # int32
    6: ("<f", 4),   # float32
    7: ("<?", 1),   # bool
    10: ("<Q", 8),  # uint64
    11: ("<q", 8),  # int64
    12: ("<d", 8),  # float64
}
_STRING, _ARRAY = 8, 9


class GGUFError(RuntimeError):
    pass


def _read(fh: BinaryIO, n: int) -> bytes:
    data = fh.read(n)
    if len(data) != n:
        raise GGUFError(f"truncated GGUF: wanted {n} bytes, got {len(data)}")
    return data


def _scalar(fh: BinaryIO, type_id: int) -> Any:
    fmt, size = _SCALARS[type_id]
    return struct.unpack(fmt, _read(fh, size))[0]


def _string(fh: BinaryIO) -> str:
    (length,) = struct.unpack("<Q", _read(fh, 8))
    return _read(fh, length).decode("utf-8", errors="replace")


def _value(fh: BinaryIO, type_id: int) -> Any:
    if type_id in _SCALARS:
        return _scalar(fh, type_id)
    if type_id == _STRING:
        return _string(fh)
    if type_id == _ARRAY:
        (elem_type,) = struct.unpack("<I", _read(fh, 4))
        (count,) = struct.unpack("<Q", _read(fh, 8))
        return [_value(fh, elem_type) for _ in range(count)]
    raise GGUFError(f"unknown GGUF value type {type_id}")


@dataclass(frozen=True)
class GGUFMetadata:
    path: Path
    version: int
    tensor_count: int
    kv: dict[str, Any]

    @property
    def architecture(self) -> str:
        return str(self.kv.get("general.architecture", "unknown"))

    def arch_key(self, suffix: str, default: Any = None) -> Any:
        return self.kv.get(f"{self.architecture}.{suffix}", default)

    @property
    def file_bytes(self) -> int:
        return self.path.stat().st_size

    # --- the five numbers §5.2 needs ---------------------------------------------------
    @property
    def n_layer(self) -> int:
        return int(self.arch_key("block_count", 0) or 0)

    @property
    def n_head(self) -> int:
        return _as_int(self.arch_key("attention.head_count", 0))

    @property
    def n_kv_head(self) -> int:
        """Grouped-query models publish one KV head count; some publish one per layer.

        A per-layer array is not an edge case to ignore — hybrid models (sliding-window or
        linear-attention layers) use it, and averaging silently under-reports KV for the
        full-attention layers. Take the max: over-budgeting KV is a slot lost, under-
        budgeting it is an OOM kill, which is a disqualification.
        """
        raw = self.arch_key("attention.head_count_kv", self.n_head)
        return _as_int(raw, reduce=max)

    @property
    def head_dim_k(self) -> int:
        explicit = _as_int(self.arch_key("attention.key_length", 0), reduce=max)
        if explicit:
            return explicit
        embed = _as_int(self.arch_key("embedding_length", 0))
        return embed // self.n_head if self.n_head else 0

    @property
    def head_dim_v(self) -> int:
        explicit = _as_int(self.arch_key("attention.value_length", 0), reduce=max)
        return explicit or self.head_dim_k

    @property
    def trained_context(self) -> int:
        return _as_int(self.arch_key("context_length", 0))

    # --- hybrid (linear-attention / SSM) layout ----------------------------------------
    @property
    def full_attention_interval(self) -> int:
        return _as_int(self.arch_key("full_attention_interval", 0))

    @property
    def n_attn_layer(self) -> int:
        """Layers whose KV grows with tokens. Hybrid models (qwen35: gated delta net)
        run full attention only every `full_attention_interval`-th layer; the rest carry
        constant-size recurrent state instead. Budgeting all layers as attention
        overstates per-token KV 4x on the shipped 4B."""
        interval = self.full_attention_interval
        return self.n_layer // interval if interval > 1 else self.n_layer

    @property
    def ssm_state_size(self) -> int:
        return _as_int(self.arch_key("ssm.state_size", 0))

    @property
    def ssm_inner_size(self) -> int:
        return _as_int(self.arch_key("ssm.inner_size", 0))

    @property
    def ssm_conv_kernel(self) -> int:
        return _as_int(self.arch_key("ssm.conv_kernel", 0))

    @property
    def ssm_group_count(self) -> int:
        return _as_int(self.arch_key("ssm.group_count", 0))

    @property
    def is_hybrid(self) -> bool:
        return self.full_attention_interval > 1 and self.ssm_state_size > 0

    def summary(self) -> str:
        return (
            f"{self.path.name}: arch={self.architecture} layers={self.n_layer} "
            f"heads={self.n_head} kv_heads={self.n_kv_head} head_dim={self.head_dim_k}"
            f"{'' if self.head_dim_v == self.head_dim_k else f'/{self.head_dim_v}'} "
            f"trained_ctx={self.trained_context} size={self.file_bytes / 2**30:.2f} GiB"
        )


def _as_int(raw: Any, *, reduce=max) -> int:
    if isinstance(raw, (list, tuple)):
        return int(reduce(raw)) if raw else 0
    return int(raw or 0)


def read_metadata(path: Path | str, *, max_kv: int = 100_000) -> GGUFMetadata:
    path = Path(path)
    with open(path, "rb") as fh:
        if _read(fh, 4) != MAGIC:
            raise GGUFError(f"{path} is not a GGUF file (bad magic)")
        version, tensor_count, kv_count = struct.unpack("<IQQ", _read(fh, 20))
        if version not in (2, 3):
            raise GGUFError(f"{path}: unsupported GGUF version {version}")
        if kv_count > max_kv:
            raise GGUFError(f"{path}: implausible metadata count {kv_count}")
        kv: dict[str, Any] = {}
        for _ in range(kv_count):
            key = _string(fh)
            (type_id,) = struct.unpack("<I", _read(fh, 4))
            value = _value(fh, type_id)
            # The tokenizer arrays are ~150k strings and nothing here needs them; keep only
            # their length so a caller can still see they exist.
            if isinstance(value, list) and len(value) > 1024:
                value = f"<array len={len(value)}>"
            kv[key] = value
        return GGUFMetadata(path=path, version=version, tensor_count=tensor_count, kv=kv)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m runtime.gguf <model.gguf> [...]", file=sys.stderr)
        return 2
    for arg in args:
        try:
            print(read_metadata(arg).summary())
        except (GGUFError, OSError) as e:
            print(f"{arg}: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
