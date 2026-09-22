"""Launch the DeepSeek native-format pilot through the frozen trainer.

This is a deliberately small adapter around ``train.py``.  It changes only
the parent/tokenizer identities and the masking function; the optimizer,
schedule, LoRA treatment and immutable run machinery remain the frozen Qwen
trainer.  The wrapper and native masker are included in every source receipt.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from . import deepseek_tokenization, train
except ImportError:  # direct, portable invocation on a training host
    import deepseek_tokenization
    import train


DEEPSEEK_TREE = "6e7d20161a524c07c6affa8e89badc7dd23aab11d2fa4ab48fcdcb7e81666133"
DEEPSEEK_TOKENIZER_FILES = {
    "tokenizer.json": "88145e3c3249adc2546ede277e9819d6e405e19072456e4b521cbc724bd60773",
    "tokenizer_config.json": "8ac8c85fb242563c2260baec0909debd69d718af6a0b3d90e6cab62b4d341cd5",
}


def configure():
    train.BASE_TREES["deepseek_fresh"] = DEEPSEEK_TREE
    train.TOKENIZER_FILES = DEEPSEEK_TOKENIZER_FILES
    train.tokenize_messages = deepseek_tokenization.tokenize_messages
    original_sources = train.source_receipts

    def source_receipts():
        sources = original_sources()
        root = Path(__file__).resolve()
        for path in (root, root.with_name("deepseek_tokenization.py")):
            sources[path.name] = train.file_receipt(path)
        return sources

    train.source_receipts = source_receipts


def main(argv=None):
    configure()
    train.main(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    main()
