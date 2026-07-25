"""Artifact table for the offline tutor bundle (TDD T2, §4 + §10.2).

Every entry is a *pin*, not a guess: the repo id and filename below were resolved against
the live HuggingFace API (`HfApi.list_models` / `list_repo_files`) and the exact file was
confirmed to exist before being written here. `fetch_models.py` re-confirms both at run
time and refuses to download anything it cannot re-confirm.

Why the identities in the TDD are not enough on their own: "Qwen3.5-4B-Instruct" is not a
repo, "the Q4_K_M .gguf" is not a filename, and at least one artifact the TDD asks for
(a Q8_0 vision projector) **does not exist** in any first-party repo. Encoding the
resolution here, with the rejected alternatives, is what stops the next person from
re-litigating it or silently substituting a near-miss.

Planning sizes come from TDD §4. `size_mode` distinguishes a target ("approx", flagged at
±20% per T2) from a ceiling ("max", flagged only when exceeded).
"""

from __future__ import annotations

from dataclasses import dataclass

GiB = 1024**3
MiB = 1024**2

# Redistribution policy (TDD §13): permissive only. This ships to third parties on a flash
# drive, so "non-commercial" and "research only" are disqualifying, not a footnote.
ALLOWED_LICENSES = {
    "Apache-2.0",
    "MIT",
    "BSD-3-Clause",
    "BSD-2-Clause",
    "CC0-1.0",
    "CC-BY-4.0",
    "Unlicense",
}

# Canonical license text, used when the artifact repo ships no LICENSE file of its own.
# Build-time network is allowed (TDD §11.2); nothing here is read at run time.
SPDX_TEXT_URL = {
    "Apache-2.0": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    "MIT": "https://opensource.org/license/mit",
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/legalcode.txt",
}


@dataclass(frozen=True)
class LicenseSource:
    """Where the license *text* for an artifact comes from."""

    spdx: str
    repo: str | None = None  # HF repo carrying the license file, if any
    path: str | None = None  # path of that file within the repo
    url: str | None = None  # explicit URL fallback
    note: str = ""

    def locator(self) -> str:
        if self.repo and self.path:
            return f"https://huggingface.co/{self.repo}/blob/main/{self.path}"
        return self.url or SPDX_TEXT_URL.get(self.spdx, "")


@dataclass(frozen=True)
class Artifact:
    name: str
    role: str
    tier: str  # "resident" | "on-demand"
    repo: str
    dest: str  # repo-relative destination directory
    license: LicenseSource
    planning_bytes: int
    size_mode: str = "approx"  # "approx" (±20% flag) | "max" (flag only if over)

    # Exactly one of `file` / `patterns` is set.
    file: str | None = None  # single-file artifact
    patterns: tuple[str, ...] = ()  # directory artifact: allow-list globs
    ignore: tuple[str, ...] = ()  # directory artifact: deny-list globs

    flag: str | None = None  # tier B: CLI flag that enables fetching
    # Search terms used to re-derive candidates if the pin ever stops resolving.
    search: str = ""
    rejected: tuple[str, ...] = ()  # alternatives considered and why they lost
    caveats: tuple[str, ...] = ()  # things a reviewer must know before shipping this

    @property
    def is_dir(self) -> bool:
        return not self.file


# --------------------------------------------------------------------------------------
# Tier A — resident, fetched by default
# --------------------------------------------------------------------------------------

QWEN_LICENSE = LicenseSource(
    spdx="Apache-2.0",
    repo="Qwen/Qwen3.5-4B",
    path="LICENSE",
    note="GGUF repackagers ship no LICENSE file; text taken from the upstream Qwen repo "
    "whose weights they requantize. Both repos are tagged apache-2.0 on the Hub.",
)

ARTIFACTS: list[Artifact] = [
    Artifact(
        name="core",
        role="reasoning + vision backbone",
        tier="resident",
        repo="unsloth/Qwen3.5-4B-GGUF",
        file="Qwen3.5-4B-Q4_K_M.gguf",
        dest="models/core",
        license=QWEN_LICENSE,
        planning_bytes=int(2.5 * GiB),
        search="Qwen3.5-4B GGUF",
        rejected=(
            "bartowski/Qwen_Qwen3.5-4B-GGUF — equivalent stock Q4_K_M, fewer downloads; "
            "kept as the fallback pin if unsloth ever rewrites the file.",
            "Qwen/Qwen3.5-4B — upstream safetensors, no GGUF; wrong format for llama.cpp.",
        ),
        caveats=(
            "D1 (TDD §14) is still open: the shipped quant is decided by the bake-off, not "
            "here. This pin is the *stock* candidate; --quant-variants fetches the others.",
        ),
    ),
    Artifact(
        name="mmproj",
        role="vision projector (image -> embedding sequence) for CORE-VISION",
        tier="resident",
        repo="unsloth/Qwen3.5-4B-GGUF",
        # NOTE: the TDD asks for Q8_0. No first-party Q8_0 mmproj exists — see UNRESOLVED
        # below. F16 is the smallest precision any trustworthy publisher ships, and it is
        # only reachable behind an explicit --mmproj-precision flag.
        file="mmproj-F16.gguf",
        dest="models/core",
        license=QWEN_LICENSE,
        planning_bytes=int(0.5 * GiB),
        # Broad on purpose: the Hub's search does not index filenames, so the useful
        # candidate list is "repos that might carry a projector", not "repos named mmproj".
        search="Qwen3.5-4B GGUF",
        rejected=(
            "mmproj-BF16.gguf (0.629 GiB) — same size as F16, worse CPU support.",
            "mmproj-F32.gguf (1.242 GiB) — double the RAM for no accuracy that survives a "
            "Q4_K_M backbone.",
            "prithivMLmods/Qwen3.5-4B-f32-GGUF mmproj-q8_0.gguf — the only Q8_0 projector "
            "for *stock* Qwen3.5-4B, but a single low-trust uploader; unverified provenance "
            "for a file that processes student photos.",
            "mradermacher/* and ZuzeTt/* Q8_0 projectors — all belong to abliterated / "
            "'heretic' / roleplay finetunes, not stock Qwen3.5-4B. Wrong model, and "
            "categorically unshippable in a children's tutor.",
        ),
        caveats=(
            "F16 costs +0.13 GiB over the TDD's Q8_0 planning figure, which is what pushes "
            "the resident tier past the 3.3 GiB acceptance cap. Resolving this needs either "
            "a self-quantized projector (llama-quantize on mmproj-F16) or a smaller core.",
        ),
    ),
    Artifact(
        name="asr",
        role="streaming English speech -> text",
        tier="resident",
        repo="csukuangfj/sherpa-onnx-moonshine-tiny-en-int8",
        patterns=("*.onnx", "tokens.txt", "LICENSE", "README.md"),
        ignore=("test_wavs/*",),
        dest="models/asr/moonshine-tiny-en-int8",
        license=LicenseSource(
            spdx="MIT",
            repo="csukuangfj/sherpa-onnx-moonshine-tiny-en-int8",
            path="LICENSE",
            note="MIT, (c) 2024 Useful Sensors — verified from the repo's own LICENSE file.",
        ),
        planning_bytes=100 * MiB,
        size_mode="max",
        search="sherpa-onnx moonshine tiny en int8",
        rejected=(
            "UsefulSensors/moonshine-tiny — upstream PyTorch, not a sherpa-onnx export.",
            "onnx-community/moonshine-tiny-ONNX — ONNX but not the 4-file sherpa layout "
            "(preprocess / encode / cached_decode / uncached_decode).",
        ),
        caveats=(
            "Model files total ~118 MiB, over the TDD's '<100 MiB' planning figure. That "
            "figure was a [MEASURE] placeholder; this is the measured value.",
        ),
    ),
    Artifact(
        name="vad",
        role="voice activity detection / utterance endpointing",
        tier="resident",
        repo="istupakov/silero-vad-onnx",
        file="silero_vad.onnx",
        dest="models/asr",
        license=LicenseSource(
            spdx="MIT",
            repo="istupakov/silero-vad-onnx",
            path="LICENSE.txt",
            note="Silero VAD is MIT upstream (snakers4/silero-vad).",
        ),
        planning_bytes=2 * MiB,
        search="silero vad onnx",
        rejected=(
            "csukuangfj/vad — the sherpa-onnx docs' usual source and it does contain "
            "silero_vad.onnx, but the repo ships NO license file and carries no license "
            "tag. Rejected on licence hygiene: TDD §13 requires a recorded license per "
            "shipped artifact, and 'everyone knows it's MIT' is not a record.",
            "onnx-community/silero-vad — MIT and well-formed, but names the file "
            "onnx/model.onnx and ships quantized variants; sherpa-onnx wants silero_vad.onnx.",
        ),
        caveats=(
            "Same upstream model as the sherpa-onnx zoo copy, different mirror. "
            "verify_models.py instantiates it through sherpa-onnx to prove compatibility "
            "rather than assuming it.",
        ),
    ),
    Artifact(
        name="tts",
        role="default text -> speech voice",
        tier="resident",
        repo="csukuangfj/vits-piper-en_US-joe-medium",
        patterns=("*.onnx", "*.onnx.json", "tokens.txt", "MODEL_CARD", "espeak-ng-data/*"),
        dest="models/tts/piper",
        license=LicenseSource(
            spdx="CC0-1.0",
            repo="csukuangfj/vits-piper-en_US-joe-medium",
            path="MODEL_CARD",
            note="Voice trained on the NabuCasa voice-datasets 'joe' set, released CC0 "
            "(public domain dedication) per the repo MODEL_CARD.",
        ),
        planning_bytes=75 * MiB,
        search="vits-piper en_US medium",
        rejected=(
            "en_US-lessac-medium — the usual Piper default and the one most guides pick, "
            "but it is trained on the Blizzard 2013 Lessac corpus under a restrictive CSTR "
            "research licence. NOT redistributable in this bundle. This is the trap in "
            "this artifact.",
            "en_US-ryan-medium — CC BY-NC-SA 4.0 (non-commercial). Rejected.",
            "en_US-hfc_female/hfc_male-medium — CC BY-NC-SA 4.0 (Hi-Fi Captain). Rejected.",
            "en_US-amy-medium / en_US-kusal-medium — model card says only 'See URL'; "
            "unresolvable licence, so unshippable.",
            "en_US-libritts_r-medium — CC BY 4.0 and acceptable, but multi-speaker (less "
            "deterministic for a tutor) and 75 MiB of model vs joe's 60 MiB. Best fallback.",
            "en_US-norman/john/kristin-medium — LibriVox public domain, also acceptable fallbacks.",
        ),
        caveats=(
            "espeak-ng-data (~17 MiB) is included because the Piper phonemizer needs it at "
            "run time and the bundle is offline.",
        ),
    ),
    Artifact(
        name="embed",
        role="query-time embeddings for RAG",
        tier="resident",
        repo="CompendiumLabs/bge-small-en-v1.5-gguf",
        file="bge-small-en-v1.5-q8_0.gguf",
        dest="models/embed",
        license=LicenseSource(
            spdx="MIT",
            repo="BAAI/bge-small-en-v1.5",
            path=None,
            url="https://huggingface.co/BAAI/bge-small-en-v1.5",
            note="BAAI ships bge-small-en-v1.5 under MIT (Hub license tag); the GGUF "
            "repackager carries the same tag and no LICENSE file.",
        ),
        planning_bytes=35 * MiB,
        search="bge-small-en-v1.5 gguf",
        rejected=(
            "unsloth/bge-small-en-v1.5-GGUF — far more downloads, but ships ONLY f16 "
            "(63 MiB). The TDD budgets Q8_0 at ~35 MiB; popularity does not override the "
            "requested quant.",
            "BAAI/bge-small-en-v1.5 — upstream safetensors; would need a third inference "
            "stack (TDD §4.8 explicitly rejects that).",
        ),
    ),
]

# --------------------------------------------------------------------------------------
# Tier B — resolved and recorded always, fetched only behind a flag
# --------------------------------------------------------------------------------------

ARTIFACTS += [
    Artifact(
        name="asr-multi",
        role="multilingual ASR (52 languages), replaces Moonshine when enabled",
        tier="on-demand",
        repo="ggml-org/Qwen3-ASR-0.6B-GGUF",
        file="Qwen3-ASR-0.6B-Q8_0.gguf",
        dest="models/asr/qwen3-asr-0.6b",
        license=LicenseSource(
            spdx="Apache-2.0",
            repo="Qwen/Qwen3-ASR-0.6B",
            path=None,
            url="https://huggingface.co/Qwen/Qwen3-ASR-0.6B",
            note="UNCONFIRMED for the GGUF repackage: ggml-org/Qwen3-ASR-0.6B-GGUF carries "
            "no license tag and no LICENSE file. Apache-2.0 is inherited from the upstream "
            "Qwen repo. Must be confirmed before this artifact ships.",
        ),
        planning_bytes=int(0.7 * GiB),
        flag="--with-multilingual-asr",
        search="Qwen3-ASR-0.6B",
        rejected=(
            "Qwen/Qwen3-ASR-0.6B — upstream safetensors, 1.75 GiB, needs a transformers "
            "runtime we do not ship.",
            "handy-computer/Qwen3-ASR-0.6B-gguf — apache-2.0 tagged (better licence "
            "provenance) but Q8_0 is 0.792 GiB. Preferred pin if the ggml-org licence "
            "cannot be confirmed.",
        ),
        caveats=(
            "Needs mmproj-Qwen3-ASR-0.6B-Q8_0.gguf (0.200 GiB) alongside the weights; "
            "true cost is ~0.95 GiB, not 0.75. Mutually exclusive with CORE-VISION at "
            "8 GiB (TDD §4.5).",
        ),
    ),
    Artifact(
        name="tts-premium",
        role="high-quality English TTS for the solo-demo profile",
        tier="on-demand",
        repo="csukuangfj/kokoro-en-v0_19",
        patterns=("*.onnx", "voices.bin", "tokens.txt", "LICENSE", "espeak-ng-data/*"),
        dest="models/tts/kokoro",
        license=LicenseSource(
            spdx="Apache-2.0",
            repo="csukuangfj/kokoro-en-v0_19",
            path="LICENSE",
            note="Apache-2.0, verified from the repo's own LICENSE file.",
        ),
        planning_bytes=330 * MiB,
        flag="--with-kokoro",
        search="kokoro sherpa-onnx",
        rejected=(
            "hexgrad/Kokoro-82M — upstream PyTorch, not a sherpa-onnx export.",
            "onnx-community/Kokoro-82M-v1.0-ONNX — ONNX but lacks the voices.bin + tokens "
            "layout sherpa-onnx expects.",
            "csukuangfj/kokoro-multi-lang-v1_0 — multilingual, larger; D5 only needs English.",
        ),
    ),
    Artifact(
        name="draft",
        role="draft model for speculative decoding (D2-b) + hint mode",
        tier="on-demand",
        repo="unsloth/Qwen3.5-0.8B-GGUF",
        file="Qwen3.5-0.8B-Q4_K_M.gguf",
        dest="models/draft",
        license=LicenseSource(
            spdx="Apache-2.0",
            repo="Qwen/Qwen3.5-0.8B",
            path=None,
            url="https://huggingface.co/Qwen/Qwen3.5-0.8B",
            note="Upstream Qwen3.5-0.8B is apache-2.0; the GGUF repo carries the same tag.",
        ),
        planning_bytes=int(0.6 * GiB),
        flag="--with-draft",
        search="Qwen3.5-0.8B GGUF",
        caveats=(
            "TDD §4.4 admission rule: adopt only if measured speedup >= 1.43x per GiB spent. "
            "Fetching it does not mean shipping it.",
        ),
    ),
]

# --------------------------------------------------------------------------------------
# D1 bake-off candidates (--quant-variants)
# --------------------------------------------------------------------------------------
# Fetched side by side into models/core/candidates/. The harness scores them and the winner
# is copied VERBATIM into models/core/ (TDD §11.3) — nothing rewrites the scored file.

QUANT_VARIANTS: list[Artifact] = [
    Artifact(
        name="core-cand-stock-q4km",
        role="D1 candidate: stock Q4_K_M",
        tier="on-demand",
        repo="unsloth/Qwen3.5-4B-GGUF",
        file="Qwen3.5-4B-Q4_K_M.gguf",
        dest="models/core/candidates",
        license=QWEN_LICENSE,
        planning_bytes=int(2.5 * GiB),
        flag="--quant-variants",
    ),
    Artifact(
        name="core-cand-unsloth-ud-q4kxl",
        role="D1 candidate: Unsloth dynamic UD-Q4_K_XL",
        tier="on-demand",
        repo="unsloth/Qwen3.5-4B-GGUF",
        file="Qwen3.5-4B-UD-Q4_K_XL.gguf",
        dest="models/core/candidates",
        license=QWEN_LICENSE,
        planning_bytes=int(2.7 * GiB),
        flag="--quant-variants",
        caveats=(
            "TDD §4.1: UD _XL files can carry f16 tensors that ik_llama.cpp (engine "
            "variant B) refuses. If this wins D1, the demo binary may differ from the "
            "scored binary.",
        ),
    ),
    Artifact(
        name="core-cand-bf16-imatrix-source",
        role="D1 candidate source: BF16 weights for our own WAEC-calibrated imatrix quant",
        tier="on-demand",
        repo="unsloth/Qwen3.5-4B-GGUF",
        file="Qwen3.5-4B-BF16.gguf",
        dest="models/core/candidates",
        license=QWEN_LICENSE,
        planning_bytes=int(7.85 * GiB),
        flag="--quant-variants",
        caveats=(
            "7.85 GiB and NOT shipped — it is the llama-quantize input for the imatrix "
            "candidate, consumed on the build machine only.",
        ),
    ),
]

# --------------------------------------------------------------------------------------
# Unresolved — deliberately NOT auto-substituted (T2 hard rule 1)
# --------------------------------------------------------------------------------------

UNRESOLVED: dict[str, str] = {
    "mmproj-q8_0": (
        "TDD §4.2 specifies a Q8_0 vision projector for Qwen3.5-4B at 0.5 GiB. No such file "
        "exists in any first-party repo (Qwen, unsloth, bartowski, lmstudio-community all "
        "publish only BF16/F16/F32). Every Q8_0 mmproj on the Hub belongs to a third-party "
        "derivative (abliterated / 'heretic' / roleplay finetunes) and is therefore a "
        "different model. Refusing to substitute silently; pass --mmproj-precision f16 to "
        "accept the 0.626 GiB F16 projector, or quantize mmproj-F16.gguf locally."
    ),
}

BY_NAME = {a.name: a for a in ARTIFACTS + QUANT_VARIANTS}
