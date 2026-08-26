#!/usr/bin/env python3
"""Generate and validate Muta's machine-assisted offline UI catalogs.

Google browser output is collected by ``browser_translate_ui_catalogs.mjs``. This script adds the
exact NLLB languages that Google does not provide, applies the final acceptance boundary, and emits
the static JavaScript asset plus readiness metadata used by the product and tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOOGLE_CACHE = Path("/tmp/muta-google-translations.json")
NLLB_CACHE = Path("/tmp/muta-nllb-translations.json")
MODEL_NAME = "facebook/nllb-200-distilled-600M"
SEMANTIC_CHANGES = json.loads((ROOT / "ui/i18n-semantic-changes.json").read_text())
SEMANTIC_CHANGE_KEYS = frozenset(SEMANTIC_CHANGES)
SEMANTIC_OVERRIDES = json.loads((ROOT / "ui/locale-semantic-overrides.json").read_text())
HOST_CAPACITY_WARNING_KEY = "host.capacityInsufficient"
HOST_CAPACITY_WARNING_OVERRIDES = json.loads(
    (ROOT / "ui/locale-host-capacity-warning.json").read_text()
)

EXISTING_READY = {"ar", "de", "en", "fr", "sw", "yo"}
HAND_RELEASE_OVERRIDE_KEYS = SEMANTIC_CHANGE_KEYS
HAND_REPAIR_OVERRIDE_KEYS = frozenset({"voice.listening"})
NLLB_TARGETS = {
    "kab": "kab_Latn",
    "kbp": "kbp_Latn",
    "kea": "kea_Latn",
    "kmb": "kmb_Latn",
    "mos": "mos_Latn",
    "umb": "umb_Latn",
}
SCRIPT_REPAIR_TARGETS = {
    "am": ("amh_Ethi", re.compile(r"[\u1200-\u137f]")),
    "ti": ("tir_Ethi", re.compile(r"[\u1200-\u137f]")),
}
NLLB_PARAPHRASES = {
    "settings.languageHelp": (
        "Choose the language for Muta's menus and answers. Auto uses the browser language for "
        "menus and the newest message language for answers."
    ),
    "settings.parallelHelp": (
        "Start a second answer while the first continues. Both answers share the local processor, "
        "so they may be slower."
    ),
    "queue.waiting": (
        "Other answers are running. Your answer starts automatically when a place is free."
    ),
    "queue.position": (
        "Queue position {position}. Other answers are running. Your answer starts when a place is free."
    ),
    "queue.discardedOne": "Removed {count} waiting messages.",
    "queue.discardedMany": "Removed {count} waiting messages.",
    "reply.parallelDisabled": (
        "Another chat is answering. Turn on multiple chats in Settings to continue here."
    ),
    "reply.voiceTyped": "Stop voice mode before typing a message.",
    "attachment.imageRead": "Image read. Ask a question, then send it.",
}
PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z][\w]*\}")
LONG_SENTINEL_RE = re.compile(r"86\d{8}")
REPEATED_PHRASE_RE = re.compile(r"(?i)(\b(?:\S+\s+){2,8}\S+)(?:\s+\1){2,}")
REPEATED_WORD_RE = re.compile(r"(?iu)\b([^\W\d_]+)\b(?:\s+\1\b){2,}")
ROW_MARKER_RE = re.compile(r"(?:^|\s)\d{3,4}\s*[:፡]")
ENGLISH_FRAGMENT_RE = re.compile(
    r"Couldn[’']t (?:start|stop)|Show more|Select the local tutor model|"
    r"Web grounding (?:on|off)|sources will cited|I[’']m still listening|"
    r"operator[’']s fixed inference-slot|shared tutor model|Enter to send|"
    r"Ctrl\+Enter to interrupt|Ground answers|off by default|Tokens per second|"
    r"Loading \{model\}|offline · local CPU|backend process tree|\(voice loop\)",
    re.IGNORECASE,
)

# Browser MT occasionally returns a short English label unchanged even when the surrounding
# catalog is translated. These corrections were checked in context and remain here so rebuilding
# from a translation checkpoint cannot reintroduce the learner-visible fallback.
CATALOG_CORRECTIONS = {
    "am": {
        "conversation.cancel": "ተወው",
        "conversation.confirmDelete": "ስረዛን አረጋግጥ",
        "conversation.pinned": "ተያይዟል",
        "power.rate": "{watts} ዋት",
        "power.plugged": "ከኃይል ጋር ተገናኝቷል",
        "resources.delete": "ሰርዝ",
        "startup.progress": "ደረጃ {stage}፣ {percent}%",
        "voice.listening": "በማዳመጥ ላይ… ሲጨርሱ ማይክራፎኑን ጠቅ ያድርጉ።",
    },
    "ar": {
        "composer.placeholder": "اسأل أي شيء",
        "resources.empty": "لا توجد موارد تعليمية بعد.",
        "resources.processing": "جارٍ التحضير…",
        "rag.pickerClosed": "أُغلق منتقي المستندات.",
        "rag.sourcePage": "{title}، صفحة PDF {page}",
        "sidebar.hostLocal": "مضيف Muta: هذا الجهاز. يعمل محليًا.",
        "account.host": "المضيف",
        "host.off": "وضع المضيف متوقف.",
        "host.noFingerprint": "بصمة الشهادة غير متاحة",
    },
    "ak": {
        "model.operatorOnly": (
            "Laptop no sohwɛfo nko ara na obetumi asesa ɔkyerɛkyerɛfo nhwɛso a "
            "obiara de di dwuma no."
        ),
    },
    "bm": {
        "web.title": "Dugukolo kan jaabiw ni ɛntɛrinɛti ye (a dabalilen tɛ)",
    },
    "crs": {
        "nav.aboutMuta": "Lo Muta",
        "model.loadingNamed": "Pe sarz {model}…",
        "web.off": "Sipor lo entènèt in dezaktive.",
    },
    "mfe": {
        "web.off": "Sipor lor web dezaktive.",
    },
    "dyu": {
        "web.title": (
            "Kɔrɔbɔli min b'a to mɔgɔ be se k'a ka ɲiningaliw jaabi n'a be "
            "ɛntɛrɛnɛti kan (a be bali ka kuma)"
        ),
    },
    "ff": {
        "web.title": (
            "Jaabawol lesdi e geese so aɗa e laylaytol (ko daaƴaaɗo e fuɗɗoode)"
        ),
    },
    "es": {
        "account.host": "Anfitrión",
    },
    "de": {
        "composer.placeholder": "Frag etwas",
        "voice.listening": "Hört zu… Klicke auf das Mikrofon, wenn du fertig bist.",
    },
    "fr": {
        "composer.placeholder": "Posez votre question",
        "resources.processing": "Préparation…",
        "rag.pickerClosed": "Sélecteur de documents fermé.",
        "voice.listening": "Écoute… Cliquez sur le microphone quand vous avez terminé.",
    },
    "lg": {
        "web.title": (
            "Eby’okuddamu bibee n’obujulizi obuva ku mutimbagano "
            "(byazikiriziddwa ku ntandikwa)"
        ),
    },
    "ig": {
        "country.southAfrica": "Mba Ndịda Afrịka",
        "nav.home": "Ụlọ Muta",
    },
    "lua": {
        "model.loadingNamed": "Kulongesha {model}…",
        "composer.placeholder": (
            "Lomba tshintu tshionso — Buela bua kutuma (kuenza mitshipu paudi "
            "uandamuna), Ctrl+Buela bua kuimanyika ne kutuma"
        ),
    },
    "om": {
        "telemetry.tpsTitle": "Sa'aatii tokko keessatti mallattoowwan (dubbii kana)",
        "web.title": (
            "Deebiiwwan lafa irraa intarneetiidhaan yeroo intarneetiidhaan kennaman "
            "(dhabdee irraa kan ka'e)"
        ),
        "web.off": "Walitti bu'iinsi weebsaayitii hin jiru.",
    },
    "ny": {
        "country.southAfrica": "Afrika ya Kumwera",
    },
    "rn": {
        "conversation.cancel": "Kureka",
        "conversation.confirmDelete": "Emeza gusiba",
        "resources.delete": "Siba",
    },
    "rw": {
        "startup.finishing": "Birarangira…",
        "startup.ready": "Muta iriteguye",
        "resources.ready": "Igikoresho kiriteguye",
    },
    "sn": {
        "country.southAfrica": "Chamhembe kweAfrica",
        "settings.interface": "Chimiro",
        "settings.general": "Zvakajairika",
        "startup.progress": "{stage}, {percent}%",
        "telemetry.peak": "yepamusoro",
        "telemetry.throttle": "kuderedza kumhanya",
        "conversation.pin": "Pina chat",
        "conversation.chats": "Machati",
        "conversation.cancel": "Kanzura",
        "conversation.confirmDelete": "Dzima",
        "network.offline": "kunze kweindaneti",
        "rag.previewLabel": "Chirevo {number}",
        "power.eco": "Maitiro eEco",
        "power.critical": "Maitiro ebhatiri rakaderera zvikuru",
        "power.actions": "Zviri kushanda: {actions}",
        "power.action_limit_response_length": "mhinduro pfupi",
        "power.action_direct_responses": "mhinduro dzakananga",
        "power.openSettings": "Vhura marongero emagetsi",
        "account.host": "Muridzi",
        "host.title": "Maitiro emuridzi",
        "host.joinUrl": "Kero yekupinda muMuta",
        "host.accountCount": "{count} akaundi",
        "host.accountCountMany": "{count} maakaundi",
        "access.password": "Pasiwedhi",
        "web.title": "Mhinduro dzepasi pawebhu paunenge uri paIndaneti (zvisingaiti)",
        "web.off": "Kutsigirwa newebhu kwakadzimwa.",
        "badge.verified": "✓ matanho akaongororwa",
    },
    "so": {
        "nav.home": "Bogga hore ee Muta",
    },
    "st": {
        "conversation.cancel": "Khansela",
        "conversation.confirmDelete": "Netefatsa ho hlakola",
        "telemetry.throttleTitle": "Ho fokotsa lebelo ka lebaka la mocheso",
    },
    "sw": {
        "composer.placeholder": "Uliza chochote",
    },
    "tn": {
        "conversation.pinned": "E kokotetswe",
        "power.plugged": "E gokagantswe le motlakase",
    },
    "xh": {
        "composer.placeholder": "Buza nantoni na",
    },
    "yo": {
        "composer.placeholder": "Béèrè ohunkóhun",
        "resources.uploadFailed": "Ìrùsókè kùnà. Gbìyànjú lẹ́ẹ̀kan sí i.",
        "resources.loadFailed": "A kò lè ṣàkójọ àwọn ohun èlò ìkẹ́kọ̀ọ́.",
    },
    "zu": {
        "composer.placeholder": "Buza noma yini",
    },
}
SEMANTICALLY_DISTINCT_KEY_PAIRS = (
    ("model.readyNew", "model.ready"),
    ("settings.saveFailed", "voice.didNotCatch"),
    ("conversation.cancel", "conversation.confirmDelete"),
    ("conversation.cancel", "resources.delete"),
    ("conversation.pinned", "power.plugged"),
    ("startup.finishing", "startup.ready"),
    ("resources.uploadFailed", "resources.loadFailed"),
)
SHORT_UI_KEYS_REQUIRING_TRANSLATION = {
    "country.southAfrica",
    "nav.aboutMuta",
    "nav.home",
    "settings.general",
    "model.loadingNamed",
    "web.off",
    "badge.verified",
    "telemetry.throttleTitle",
}
# "General" is also the ordinary Spanish translation, not an English fallback.
EXACT_ENGLISH_EQUIVALENTS = {"es": {"settings.general"}}
# These browser-MT packs still contain learner-facing English clauses after targeted retries.
# Keep them registered internally, but do not advertise them as complete UI languages until a
# native review/retranslation replaces the checkpoint.
REVIEW_REJECTED = {
    "ak",
    "bci",
    "bm",
    "crs",
    "dyu",
    "ee",
    "fon",
    "kri",
    "lg",
    "ln",
    "lua",
    "mfe",
    "nr",
    "nso",
    "nus",
    "om",
    "sg",
    "ti",
    "ts",
    "ve",
    "wo",
}


def _node_json(expression: str) -> Any:
    setup = """
globalThis.MutaAfricaLanguages=require('./ui/africa-languages.js');
globalThis.MutaInterfaceLocales=require('./ui/locale-manifest.js');
globalThis.MutaI18n=require('./ui/i18n.js');
"""
    result = subprocess.run(
        ["node", "-e", setup + f"process.stdout.write(JSON.stringify({expression}));"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def english_catalog() -> dict[str, str]:
    return _node_json("MutaI18n.catalogs.en")


def registry_languages() -> list[dict[str, Any]]:
    return _node_json("MutaAfricaLanguages.languages")


def hand_catalogs() -> dict[str, dict[str, str]]:
    script = """
globalThis.MutaAfricaLanguages = require('./ui/africa-languages.js');
globalThis.MutaInterfaceLocales = require('./ui/locale-manifest.js');
globalThis.MutaI18n = require('./ui/i18n.js');
globalThis.window = globalThis;
require('./ui/locale-fr.js');
require('./ui/locales.js');
process.stdout.write(JSON.stringify(MutaI18n.catalogs));
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def emitted_candidates() -> dict[str, Any]:
    """Recover the committed catalogs so ``--emit`` works from a clean checkout.

    Browser/model caches live outside the repository because they are collection checkpoints, not
    product inputs. The accepted static asset is the durable source between translation runs.
    """

    asset_path = ROOT / "ui/locale-generated.js"
    metadata_path = ROOT / "ui/locale-generated.meta.json"
    if not asset_path.exists() or not metadata_path.exists():
        return {}
    script = """
const captured = {};
globalThis.window = globalThis;
globalThis.MutaI18n = {
  registerLocale(definition, messages) {
    captured[definition.tag] = messages;
  },
  initialize() {},
};
require('./ui/locale-generated.js');
process.stdout.write(JSON.stringify(captured));
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    messages_by_tag = json.loads(result.stdout)
    metadata_root = json.loads(metadata_path.read_text())
    metadata = {
        **metadata_root.get("generated", {}),
        **metadata_root.get("overlays", {}),
    }
    return {
        tag: {**metadata[tag], "messages": messages}
        for tag, messages in messages_by_tag.items()
        if tag in metadata
    }


def emitted_hidden_reasons(valid_keys: set[str]) -> dict[str, list[str]]:
    path = ROOT / "ui/locale-generated.meta.json"
    if not path.exists():
        return {}
    hidden = json.loads(path.read_text()).get("hidden", {})
    result: dict[str, list[str]] = {}
    for tag, reasons in hidden.items():
        current: list[str] = []
        for reason in reasons:
            referenced = set(re.findall(r"[a-z][\w]*(?:\.[\w]+)+", reason))
            if referenced and not referenced.issubset(valid_keys):
                continue
            current.append(reason)
        if current:
            result[tag] = current
    return result


def placeholders(value: str) -> list[str]:
    return sorted(PLACEHOLDER_RE.findall(value))


def sample_source(key: str, value: str) -> tuple[str, list[tuple[str, str]]]:
    if key == "thinking.seconds":
        value = "Thought for {seconds} seconds."
    elif key == "thinking.minutes":
        value = "Thought for {minutes} minutes and {seconds} seconds."
    elif key in {"queue.discardedOne", "queue.discardedMany"}:
        value = "Discarded {count} queued messages."
    elif key == "queue.waitingSlot":
        value = "Queue position {position}. Waiting for a free place."
    samples = ["17017", "29029", "43043", "61061"]
    replacements: list[tuple[str, str]] = []
    for index, placeholder in enumerate(placeholders(value)):
        sample = samples[index]
        value = value.replace(placeholder, sample)
        replacements.append((sample, placeholder))
    return value, replacements


def restore_samples(value: str, replacements: list[tuple[str, str]]) -> str | None:
    for sample, placeholder in replacements:
        if sample not in value:
            return None
        value = value.replace(sample, placeholder, 1)
    return value


def run_nllb() -> None:
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    english = english_catalog()
    cache: dict[str, Any] = json.loads(NLLB_CACHE.read_text()) if NLLB_CACHE.exists() else {}
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, src_lang="eng_Latn")
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    model.eval()

    for tag, target_code in NLLB_TARGETS.items():
        existing = cache.get(tag, {})
        if (
            existing
            and not existing.get("errors")
            and set(existing.get("messages", {})) == set(english)
        ):
            continue
        keys = [key for key in english if key not in existing.get("messages", {})]
        sources: list[str] = []
        replacement_rows: list[list[tuple[str, str]]] = []
        for key in keys:
            source, replacements = sample_source(key, english[key])
            sources.append(source)
            replacement_rows.append(replacements)

        messages: dict[str, str] = dict(existing.get("messages", {}))
        errors: list[str] = []
        forced_bos = tokenizer.convert_tokens_to_ids(target_code)
        for start in range(0, len(keys), 8):
            source_batch = sources[start : start + 8]
            inputs = tokenizer(
                source_batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512,
            ).to(device)
            with torch.inference_mode():
                generated = model.generate(
                    **inputs,
                    forced_bos_token_id=forced_bos,
                    max_new_tokens=256,
                    num_beams=2,
                    early_stopping=True,
                )
            decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
            for offset, translated in enumerate(decoded):
                index = start + offset
                restored = restore_samples(translated.strip(), replacement_rows[index])
                key = keys[index]
                if restored is None:
                    errors.append(f"placeholder:{key}")
                    restored = translated.strip()
                messages[key] = restored
        cache[tag] = {
            "provenance": f"nllb:{MODEL_NAME}",
            "target": target_code,
            "messages": messages,
            "errors": errors,
        }
        NLLB_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n")
        print(f"{tag}: {len(messages)} keys, {len(errors)} errors")


def repair_nllb() -> None:
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    if not NLLB_CACHE.exists():
        raise SystemExit("NLLB cache does not exist; run --nllb first")
    english = english_catalog()
    cache: dict[str, Any] = json.loads(NLLB_CACHE.read_text())
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, src_lang="eng_Latn")
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    model.eval()

    for tag, result in cache.items():
        failed_keys = sorted({error.split(":", 1)[1] for error in result.get("errors", [])})
        repeated_keys = {
            key
            for key, value in result["messages"].items()
            if REPEATED_PHRASE_RE.search(value)
        }
        keys = sorted(set(failed_keys) | repeated_keys)
        if not keys:
            continue
        sources: list[str] = []
        replacement_rows: list[list[tuple[str, str]]] = []
        for key in keys:
            source, replacements = sample_source(key, NLLB_PARAPHRASES.get(key, english[key]))
            sources.append(source)
            replacement_rows.append(replacements)
        inputs = tokenizer(
            sources,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        ).to(device)
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                forced_bos_token_id=tokenizer.convert_tokens_to_ids(result["target"]),
                max_new_tokens=256,
                num_beams=3,
                early_stopping=True,
            )
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        errors: list[str] = []
        for index, key in enumerate(keys):
            restored = restore_samples(decoded[index].strip(), replacement_rows[index])
            result["messages"][key] = restored if restored is not None else decoded[index].strip()
            if restored is None:
                errors.append(f"placeholder:{key}")
        result["errors"] = errors
        NLLB_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n")
        print(f"repaired {tag}: {len(keys)} keys, {len(errors)} placeholder errors")


def repair_google_scripts() -> None:
    """Replace Google romanisation fallbacks with exact-script NLLB translations."""

    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    if not GOOGLE_CACHE.exists():
        raise SystemExit("Google cache does not exist; collect browser translations first")
    english = english_catalog()
    cache: dict[str, Any] = json.loads(GOOGLE_CACHE.read_text())
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, src_lang="eng_Latn")
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    model.eval()

    for tag, (target_code, script_pattern) in SCRIPT_REPAIR_TARGETS.items():
        result = cache[tag]
        for key, value in result["messages"].items():
            marker = ROW_MARKER_RE.search(value)
            if marker:
                result["messages"][key] = value[: marker.start()].strip()
        keys = [
            key
            for key, value in result["messages"].items()
            if re.search(r"[A-Za-z]", english[key]) and not script_pattern.search(value)
        ]
        sources: list[str] = []
        replacement_rows: list[list[tuple[str, str]]] = []
        for key in keys:
            source, replacements = sample_source(key, english[key])
            sources.append(source)
            replacement_rows.append(replacements)
        for start in range(0, len(keys), 8):
            inputs = tokenizer(
                sources[start : start + 8],
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512,
            ).to(device)
            with torch.inference_mode():
                generated = model.generate(
                    **inputs,
                    forced_bos_token_id=tokenizer.convert_tokens_to_ids(target_code),
                    max_new_tokens=256,
                    num_beams=3,
                    early_stopping=True,
                )
            decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
            for offset, translated in enumerate(decoded):
                index = start + offset
                restored = restore_samples(translated.strip(), replacement_rows[index])
                if restored is None or not script_pattern.search(restored):
                    raise SystemExit(f"script repair failed for {tag}:{keys[index]}")
                result["messages"][keys[index]] = restored
        result["provenance"] = f"google-web+nllb:{MODEL_NAME}"
        result["errors"] = []
        GOOGLE_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n")
        print(f"script-repaired {tag}: {len(keys)} keys")


def validate_catalog(
    tag: str,
    messages: dict[str, str],
    english: dict[str, str],
    *,
    strict_repetition: bool = False,
) -> list[str]:
    errors: list[str] = []
    if set(messages) != set(english):
        missing = sorted(set(english) - set(messages))
        extra = sorted(set(messages) - set(english))
        errors.append(f"key-parity:missing={missing}:extra={extra}")
        return errors
    for key, source in english.items():
        value = messages[key]
        if not isinstance(value, str) or not value.strip():
            errors.append(f"empty:{key}")
            continue
        if placeholders(value) != placeholders(source):
            errors.append(f"placeholder:{key}")
        if LONG_SENTINEL_RE.search(value) or "ZXQMUTA" in value:
            errors.append(f"sentinel:{key}")
        if ROW_MARKER_RE.search(value):
            errors.append(f"merged-row:{key}")
        if ENGLISH_FRAGMENT_RE.search(value):
            errors.append(f"english-fragment:{key}")
        if (
            "Translating..." in value
            or "Translation results" in value
            or re.search(r"\bstar_border\b", value, re.IGNORECASE)
        ):
            errors.append(f"browser-residue:{key}")
        if len(source) > 24 and len(value) < max(6, len(source) * 0.18):
            errors.append(f"too-short:{key}")
        if len(value) > max(80, len(source) * 6):
            errors.append(f"too-long:{key}")
        if len(source) > 24 and value.strip() == source.strip():
            errors.append(f"untranslated:{key}")
        if (
            key in SHORT_UI_KEYS_REQUIRING_TRANSLATION
            and value.strip() == source.strip()
            and key not in EXACT_ENGLISH_EQUIVALENTS.get(tag, set())
        ):
            errors.append(f"untranslated-short:{key}")
        if REPEATED_PHRASE_RE.search(value):
            errors.append(f"repetition:{key}")
        if REPEATED_WORD_RE.search(value):
            errors.append(f"repeated-word:{key}")
        words = re.findall(r"\w+", value.lower())
        if strict_repetition and len(words) >= 12:
            unique_ratio = len(set(words)) / len(words)
            trigrams = Counter(tuple(words[index : index + 3]) for index in range(len(words) - 2))
            repeated_trigram = max(trigrams.values(), default=0)
            if unique_ratio < 0.30 or (repeated_trigram >= 3 and unique_ratio < 0.65):
                errors.append(f"degenerate-repetition:{key}")

    joined = " ".join(messages.values())
    unchanged = [
        key
        for key, source in english.items()
        if messages[key].strip() == source.strip()
    ]
    # A few proper names and international technical loans can legitimately be identical. A pack
    # with a large cluster of English-identical labels, however, is a partial translation.
    if len(unchanged) > 12:
        errors.append(f"excessive-untranslated-labels:{len(unchanged)}")
    for left, right in SEMANTICALLY_DISTINCT_KEY_PAIRS:
        if messages[left].strip() == messages[right].strip():
            errors.append(f"semantic-collapse:{left}={right}")
    if tag in {"am", "ti"}:
        ethiopic = len(re.findall(r"[\u1200-\u137f]", joined))
        if ethiopic < 500:
            errors.append("script:expected-ethiopic")
        for key, source in english.items():
            if re.search(r"[A-Za-z]", source) and not re.search(
                r"[\u1200-\u137f]", messages[key]
            ):
                errors.append(f"script:expected-ethiopic:{key}")
    if tag == "zgh":
        tifinagh = len(re.findall(r"[\u2d30-\u2d7f]", joined))
        if tifinagh < 500:
            errors.append("script:expected-tifinagh")
    return errors


def repair_dropped_placeholders(messages: dict[str, str], english: dict[str, str]) -> None:
    """Keep a translated label usable when MT drops a display variable.

    The variable is placed at the stable leading edge instead of inventing target-language
    grammar. This is deliberately limited to compact status labels whose surrounding translation
    is otherwise complete; any other loss remains a rejection.
    """

    prefixable = {
        "model.loadingNamed",
        "model.loadingNote",
        "model.switchingNamed",
        "model.readyNew",
        "model.ready",
        "queue.position",
        "queue.waitingSlot",
        "queue.discardedOne",
        "queue.discardedMany",
    }
    for key in prefixable:
        value = messages.get(key)
        if not value:
            continue
        expected = placeholders(english[key])
        present = placeholders(value)
        missing = [placeholder for placeholder in expected if placeholder not in present]
        if missing and len(present) + len(missing) == len(expected):
            messages[key] = f"{' '.join(missing)} {value}".strip()


def repair_english_loading_prefix(messages: dict[str, str], english: dict[str, str]) -> None:
    """Reuse the translated compact loading label when browser MT leaves that prefix in English."""

    note = messages.get("model.loadingNote", "")
    translated_label = messages.get("model.loadingNamed", "")
    english_label = english["model.loadingNamed"]
    prefix = re.match(r"^Loading \{model\}(?:…|\.\.\.)\s*", note)
    if prefix and translated_label != english_label:
        messages["model.loadingNote"] = f"{translated_label} {note[prefix.end():].lstrip()}"


def repair_english_voice_suffix(messages: dict[str, str]) -> None:
    """Drop Google's untranslated explanatory suffix; the translated action remains accessible."""

    title = messages.get("voice.talkTitle", "")
    messages["voice.talkTitle"] = re.sub(
        r"\s*\(voice loop\)\s*[.!]?\s*$", "", title
    ).strip()


def repair_browser_ui_residue(messages: dict[str, str]) -> None:
    """Remove Google Translate controls accidentally copied after translated text."""

    for key, value in messages.items():
        messages[key] = re.sub(r"(?:\s|\n)*star_border(?:\s|\n)*$", "", value).strip()


def emit_assets() -> None:
    english = english_catalog()
    registry = registry_languages()
    registry_by_tag = {item["tag"]: item for item in registry}
    authored = hand_catalogs()
    prior_hidden = emitted_hidden_reasons(set(english))
    caches: list[dict[str, Any]] = [emitted_candidates()]
    for path in (GOOGLE_CACHE, NLLB_CACHE):
        if path.exists():
            caches.append(json.loads(path.read_text()))

    candidates: dict[str, Any] = {}
    for cache in caches:
        candidates.update(cache)
    accepted: dict[str, Any] = {}
    accepted_overlays: dict[str, Any] = {}
    rejected: dict[str, list[str]] = {}
    for tag, result in candidates.items():
        if tag not in registry_by_tag and tag not in EXISTING_READY:
            continue
        # Translation checkpoints may be ahead of the currently checked-out UI while another
        # feature branch is being rebased. Emit only keys in the canonical English catalog.
        messages = {
            key: value
            for key, value in dict(result.get("messages") or {}).items()
            if key in english
        }
        messages.update(CATALOG_CORRECTIONS.get(tag, {}))
        messages.update(SEMANTIC_OVERRIDES.get(tag, {}))
        if tag in HOST_CAPACITY_WARNING_OVERRIDES:
            messages[HOST_CAPACITY_WARNING_KEY] = HOST_CAPACITY_WARNING_OVERRIDES[tag]
        overlay_messages: dict[str, str] | None = None
        if tag in EXISTING_READY:
            base = authored.get(tag, {})
            overlay_messages = {
                key: value
                for key, value in messages.items()
                if key not in base
                or key in HAND_RELEASE_OVERRIDE_KEYS
                or key in HAND_REPAIR_OVERRIDE_KEYS
            }
            messages = {**base, **overlay_messages}
        repair_dropped_placeholders(messages, english)
        repair_english_loading_prefix(messages, english)
        repair_english_voice_suffix(messages)
        repair_browser_ui_residue(messages)
        if overlay_messages is not None:
            overlay_messages = {key: messages[key] for key in overlay_messages}
        result = {**result, "messages": messages}
        candidates[tag] = result
        errors = validate_catalog(
            tag,
            messages,
            english,
            strict_repetition=str(result.get("provenance", "")).startswith("nllb:"),
        )
        target_primary = str(result.get("target", "")).split("_", 1)[0].lower()
        tag_primary = tag.split("-", 1)[0].lower()
        if target_primary != tag_primary:
            errors.append(f"target-mismatch:{result.get('target')}")
        if tag in REVIEW_REJECTED:
            errors.append("native-review:untranslated-english")
        errors = sorted(set(errors))
        if errors:
            # A newly added canonical key makes parity fail before the validator can re-report
            # older per-key defects. Keep those still-valid reasons so hidden-pack metadata does
            # not become less informative merely because the interface grew by one key.
            if any(error.startswith("key-parity:") for error in errors):
                errors = sorted(set(errors) | set(prior_hidden.get(tag, [])))
            rejected[tag] = errors
        elif overlay_messages is not None:
            if overlay_messages:
                accepted_overlays[tag] = {**result, "messages": overlay_messages}
        else:
            accepted[tag] = result

    hashes: dict[str, str] = {}
    for tag, result in accepted.items():
        digest = hashlib.sha256(
            json.dumps(result["messages"], ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        if digest in hashes:
            rejected[tag] = [f"duplicate-catalog:{hashes[digest]}"]
        else:
            hashes[digest] = tag
    for tag in rejected:
        accepted.pop(tag, None)

    ordered_tags = [item["tag"] for item in registry if item["tag"] in accepted]
    overlay_tags = [tag for tag in ("ar", "sw", "yo", "fr", "de") if tag in accepted_overlays]
    visible_translated_tags = set(ordered_tags) | set(overlay_tags)
    if set(HOST_CAPACITY_WARNING_OVERRIDES) != visible_translated_tags:
        missing = sorted(visible_translated_tags - set(HOST_CAPACITY_WARNING_OVERRIDES))
        extra = sorted(set(HOST_CAPACITY_WARNING_OVERRIDES) - visible_translated_tags)
        raise SystemExit(
            f"Host capacity warning locale drift: missing={missing} extra={extra}"
        )
    if set(SEMANTIC_OVERRIDES) != visible_translated_tags:
        missing = sorted(visible_translated_tags - set(SEMANTIC_OVERRIDES))
        extra = sorted(set(SEMANTIC_OVERRIDES) - visible_translated_tags)
        diagnostics = {tag: rejected.get(tag) for tag in sorted(set(SEMANTIC_OVERRIDES) - visible_translated_tags)}
        raise SystemExit(
            f"semantic override locale drift: missing={missing} extra={extra} rejected={diagnostics}"
        )
    for tag, rows in SEMANTIC_OVERRIDES.items():
        if set(rows) != SEMANTIC_CHANGE_KEYS:
            missing = sorted(SEMANTIC_CHANGE_KEYS - set(rows))
            extra = sorted(set(rows) - SEMANTIC_CHANGE_KEYS)
            raise SystemExit(
                f"semantic override key drift for {tag}: missing={missing} extra={extra}"
            )
    packs = {tag: accepted[tag]["messages"] for tag in ordered_tags}
    packs.update({tag: accepted_overlays[tag]["messages"] for tag in overlay_tags})
    definitions = {
        tag: {"tag": tag, "direction": registry_by_tag[tag]["direction"]}
        for tag in ordered_tags
    }
    definitions.update(
        {
            tag: {
                "tag": tag,
                "direction": registry_by_tag.get(tag, {}).get("direction", "ltr"),
            }
            for tag in overlay_tags
        }
    )
    metadata = {
        "generated": {
            tag: {
                "provenance": accepted[tag]["provenance"],
                "target": accepted[tag]["target"],
                "review": "machine-assisted-spot-reviewed",
            }
            for tag in ordered_tags
        },
        "overlays": {
            tag: {
                "provenance": accepted_overlays[tag]["provenance"],
                "target": accepted_overlays[tag]["target"],
                "review": "machine-assisted-spot-reviewed",
            }
            for tag in overlay_tags
        },
        "hidden": {
            item["tag"]: rejected.get(
                item["tag"],
                prior_hidden.get(item["tag"], ["unsupported-by-translation-sources"]),
            )
            for item in registry
            if item["tag"] not in EXISTING_READY and item["tag"] not in accepted
        },
    }

    asset = """/* Machine-assisted complete offline UI catalogs.
 * Generated by scripts/generate_ui_catalogs.py; native-speaker review remains tracked separately. */
\"use strict\";

(() => {
  const i18n = window.MutaI18n;
  const definitions = __DEFINITIONS__;
  const packs = __PACKS__;
  for (const [tag, messages] of Object.entries(packs)) {
    i18n.registerLocale(definitions[tag], messages);
  }
  i18n.initialize();
  globalThis.MutaGeneratedLocaleMetadata = __METADATA__;
})();
"""
    asset = asset.replace("__DEFINITIONS__", json.dumps(definitions, ensure_ascii=False, indent=2))
    asset = asset.replace("__PACKS__", json.dumps(packs, ensure_ascii=False, indent=2))
    asset = asset.replace("__METADATA__", json.dumps(metadata, ensure_ascii=False, indent=2))
    (ROOT / "ui/locale-generated.js").write_text(asset)
    (ROOT / "ui/locale-generated.meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
    )

    ready_tags = [item["tag"] for item in registry if item["tag"] in accepted or item["tag"] in EXISTING_READY]
    ready_tags.extend(tag for tag in ("en", "de") if tag not in ready_tags)
    manifest_rows = []
    for tag in ready_tags:
        direction = registry_by_tag.get(tag, {}).get("direction", "ltr")
        manifest_rows.append(f'    Object.freeze({{ tag: "{tag}", direction: "{direction}" }}),')
    manifest = """/* Complete interface packs shared by the pre-paint bootstrap and full i18n runtime.
 * Generated catalogs are accepted only after scripts/generate_ui_catalogs.py validation. */
\"use strict\";

(() => {
  const locales = Object.freeze([
__ROWS__
  ]);
  globalThis.MutaInterfaceLocales = locales;
  if (typeof module !== \"undefined\" && module.exports) module.exports = locales;
})();
""".replace("__ROWS__", "\n".join(manifest_rows))
    (ROOT / "ui/locale-manifest.js").write_text(manifest)
    print(
        f"accepted={len(accepted) + len(EXISTING_READY)} "
        f"generated={len(accepted)} overlays={len(accepted_overlays)} "
        f"hidden={len(metadata['hidden'])}"
    )
    if rejected:
        for tag, errors in sorted(rejected.items()):
            print(f"rejected {tag}: {', '.join(errors)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nllb", action="store_true", help="translate exact NLLB target languages")
    parser.add_argument(
        "--nllb-repair",
        action="store_true",
        help="retry failed or repetitive NLLB messages with short paraphrases",
    )
    parser.add_argument(
        "--nllb-script-repair",
        action="store_true",
        help="replace Google romanisation fallbacks with exact-script NLLB output",
    )
    parser.add_argument("--emit", action="store_true", help="validate caches and emit UI assets")
    args = parser.parse_args()
    if not args.nllb and not args.nllb_repair and not args.nllb_script_repair and not args.emit:
        parser.error("choose a translation/repair action and/or --emit")
    if args.nllb:
        run_nllb()
    if args.nllb_repair:
        repair_nllb()
    if args.nllb_script_repair:
        repair_google_scripts()
    if args.emit:
        emit_assets()


if __name__ == "__main__":
    main()
