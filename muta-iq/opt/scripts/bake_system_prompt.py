#!/usr/bin/env python3
"""Bake a default system prompt into a GGUF's tokenizer.chat_template (only used when the caller
supplies no system message). Copies the file with the KV rewritten (tensors byte-identical).

Method: prepend a Jinja block that rebinds `messages` to [system] + messages when the first message
is not a system message, then the original template runs unchanged. Works with any template that
reads `messages` (jinja2 and llama.cpp's minja both support `set` with list concatenation).

Usage: bake_system_prompt.py in.gguf out.gguf --system FILE [--strip-default-qwen] [--print]
"""
import argparse, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "llama.cpp" / "gguf-py"))
import numpy as np
import gguf
from gguf import GGUFReader, GGUFWriter, GGUFValueType

MARK = "{# muta:default-system #}"

def jinja_str(s: str) -> str:
    # Jinja single-quoted string literal with escapes minja/jinja2 both accept
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n") + "'"

def chatml_template(system: str, think_default: str) -> str:
    """Clean ChatML template: persona injected when no system message, merged (prepended) when one exists;
    assistant turn starts with an empty think block unless enable_thinking is true (think_default='off'),
    or with '<think>\n' when think_default='on' and the caller did not disable it."""
    persona = jinja_str(system)
    if think_default == "off":
        # unconditional empty think block: llama.cpp's template analysis then reports thinking=0 and never
        # opens a reasoning block, whatever --reasoning / enable_thinking the front-end passes
        gen = "{%- if add_generation_prompt -%}{{ '<|im_start|>assistant\\n<think>\\n\\n</think>\\n\\n' }}{%- endif -%}"
    elif think_default == "on":
        gen = ("{%- if add_generation_prompt -%}{{ '<|im_start|>assistant\\n' }}"
               "{%- if enable_thinking is defined and enable_thinking is false -%}{{ '<think>\\n\\n</think>\\n\\n' }}"
               "{%- else -%}{{ '<think>\\n' }}{%- endif -%}{%- endif -%}")
    else:  # plain: no think block handling
        gen = "{%- if add_generation_prompt -%}{{ '<|im_start|>assistant\\n' }}{%- endif -%}"
    return (MARK +
            "{%- set persona = " + persona + " -%}"
            "{%- set ns = namespace(has_system=false) -%}"
            "{%- for m in messages if m['role'] == 'system' -%}{%- set ns.has_system = true -%}{%- endfor -%}"
            "{%- if not ns.has_system -%}{{ '<|im_start|>system\\n' + persona + '<|im_end|>\\n' }}{%- endif -%}"
            "{%- for message in messages -%}"
            "{%- if message['role'] == 'system' -%}{{ '<|im_start|>system\\n' + persona + '\\n\\n' + message['content'] + '<|im_end|>\\n' }}"
            "{%- else -%}{{ '<|im_start|>' + message['role'] + '\\n' + message['content'] + '<|im_end|>\\n' }}{%- endif -%}"
            "{%- endfor -%}" + gen)

def build(template: str, system: str) -> str:
    if MARK in template:
        raise SystemExit("template already has a muta default-system block; start from the original file")
    inject = (MARK +
              "{% if messages | length == 0 or messages[0]['role'] != 'system' %}"
              "{% set messages = [{'role': 'system', 'content': " + jinja_str(system) + "}] + messages %}"
              "{% endif %}")
    return inject + template

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp", type=Path); ap.add_argument("out", type=Path)
    ap.add_argument("--system", required=True, type=Path)
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--set-languages", default=None, help="comma list to overwrite general.languages, e.g. en")
    ap.add_argument("--replace-chatml", default=None, choices=["off","on","plain"], help="replace the template with clean ChatML+persona; value = default thinking mode")
    ap.add_argument("--set-name", default=None, help="overwrite general.name")
    ap.add_argument("--sampling", default=None, help="comma list key=value for general.sampling.* e.g. temp=0.4,top_p=0.9,min_p=0.05,penalty_repeat=1.05")
    a = ap.parse_args()
    system = a.system.read_text().strip()
    r = GGUFReader(str(a.inp))
    f = r.fields
    tf = f.get("tokenizer.chat_template")
    if tf is None:
        # no template in the file (e.g. BitCPM-CANN-3B): fall back to the MiniCPM/ChatML template
        template = ("{% for message in messages %}{{'<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>' + '\n'}}{% endfor %}"
                    "{% if add_generation_prompt %}{{ '<|im_start|>assistant\n' }}{% endif %}")
        print("note: file has no tokenizer.chat_template; using ChatML", file=sys.stderr)
    else:
        template = bytes(tf.parts[tf.data[0]]).decode("utf-8")
    new_t = chatml_template(system, a.replace_chatml) if a.replace_chatml else build(template, system)
    if a.print:
        print(new_t); return
    arch = bytes(f["general.architecture"].parts[f["general.architecture"].data[0]]).decode()
    w = GGUFWriter(str(a.out), arch)
    wrote_t = False
    samp = {}
    if a.sampling:
        for kv in a.sampling.split(","):
            k, v = kv.split("="); samp[k.strip()] = float(v)
    for fld in r.fields.values():
        name = fld.name
        if name == gguf.Keys.General.ARCHITECTURE or name.startswith("GGUF."):
            continue
        vt = fld.types[0]
        st = fld.types[-1] if vt == GGUFValueType.ARRAY else None
        if name == "tokenizer.chat_template":
            w.add_string(name, new_t); wrote_t = True; continue
        if name == "general.languages" and a.set_languages:
            w.add_array(name, a.set_languages.split(",")); continue
        if name == "general.name" and a.set_name:
            w.add_string(name, a.set_name); continue
        if name.startswith("general.sampling.") and a.sampling and name.split(".")[-1] in samp:
            w.add_float32(name, samp.pop(name.split(".")[-1])); continue
        w.add_key_value(name, fld.contents(), vt, sub_type=st)
    if not wrote_t:
        w.add_string("tokenizer.chat_template", new_t)
    for k, v in samp.items():
        w.add_float32("general.sampling." + k, v)
    w.add_string("muta.default_system_prompt", system)
    for t in r.tensors:
        w.add_tensor_info(t.name, t.data.shape, t.data.dtype, t.data.nbytes, t.tensor_type)
    w.write_header_to_file(); w.write_kv_data_to_file(); w.write_ti_data_to_file()
    for t in r.tensors:
        w.write_tensor_data(t.data, tensor_endianess=r.endianess)
    w.close()
    print(f"wrote {a.out}; template length {len(template)} -> {len(new_t)}")

if __name__ == "__main__":
    main()
