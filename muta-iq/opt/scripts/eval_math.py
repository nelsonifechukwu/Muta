#!/usr/bin/env python3
"""Bake-off harness: GSM8K subset (numeric exact-match, greedy, chat template) + saved tutoring
samples, using llama-cpp-python exactly like the profiler's accuracy stack (CPU, 4 threads).

Usage: eval_math.py --model X.gguf [--n 40] [--system FILE|none] [--max-tokens 320] [--tag T]
                    [--samples] [--think off]
Writes opt/eval/results/<tag>.json (per-item records + accuracy + tok/s) and prints a summary line
prefixed with '@@EVAL '.
"""
import argparse, json, re, sys, time, os
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent.parent   # opt/
DEFAULT_SYSTEM = (HERE / "eval" / "system_prompt.txt")

TUTOR_PROMPTS = [
    "A trader buys 24 identical crates for 18000 naira and sells them at a 25% profit. What is the selling price of one crate? Show your working.",
    "A student writes: \"A heavier ball falls faster than a lighter one, because gravity pulls harder on it.\" Identify exactly what is correct and what is mistaken in that reasoning, explain what actually determines how fast each ball accelerates, and describe an observation the student could make to test it.",
    "I keep getting the derivative of x^2 wrong. I think it's x. Can you help me see why that's wrong without just giving me the answer?",
    "In a WASSCE chemistry question: 20 cm³ of 0.1 mol/dm³ NaOH neutralises 25 cm³ of HCl. Find the concentration of the HCl and explain each step like a teacher would.",
    "Solve x^2 - 5x + 6 = 0 and show me how to check that the answers are right.",
    "I think 1/2 + 1/3 = 2/5. Where did I go wrong?",
    "A car starts from rest and accelerates uniformly at 2 m/s^2 for 10 seconds. How far does it travel? Explain which equation of motion you used and why.",
    "Ada saves 5000 cedis at 8% simple interest per year. How much interest does she earn in 3 years, and how would compound interest be different?",
    "Explain photosynthesis to a JSS3 student and give the word equation and the balanced chemical equation.",
    "Why is the sky blue? Give the real reason and one common wrong explanation students give.",
]

def last_number(text: str):
    # prefer "Final answer: X" / "#### X" patterns, else last number in text
    m = re.findall(r"(?:final answer|answer)\s*[:=]\s*\$?\s*(-?[\d,]*\.?\d+)", text, flags=re.I)
    if m:
        s = m[-1]
    else:
        m = re.findall(r"-?[\d,]*\.?\d+", text)
        if not m:
            return None
        s = m[-1]
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None

def gold(answer: str):
    return float(answer.split("####")[-1].strip().replace(",", ""))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--system", default=str(DEFAULT_SYSTEM))
    ap.add_argument("--max-tokens", type=int, default=320)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--samples", action="store_true", help="also generate the 4 tutoring prompts (saved verbatim)")
    ap.add_argument("--think", default="off", help="off|on|auto: value of enable_thinking passed to the chat template")
    ap.add_argument("--n-ctx", type=int, default=2048)
    a = ap.parse_args()
    from llama_cpp import Llama
    tag = a.tag or Path(a.model).stem
    out_dir = HERE / "eval" / "results"; out_dir.mkdir(parents=True, exist_ok=True)
    system = None
    if a.system and a.system != "none" and Path(a.system).exists():
        system = Path(a.system).read_text().strip()
    df = pd.read_parquet(HERE / "eval" / "gsm8k" / "main" / "test-00000-of-00001.parquet")
    df = df.sample(n=a.n, random_state=a.seed)
    # llama-cpp-python falls back to the llama-2 format when a GGUF has no chat_template; MiniCPM/BitCPM files
    # without one need ChatML. Detect from the header.
    chat_format = None
    try:
        import struct
        sys.path.insert(0, "/Users/timii/Developer/Muta/muta-iq/opt/llama.cpp/gguf-py")
        from gguf import GGUFReader
        rr = GGUFReader(a.model)
        if "tokenizer.chat_template" not in rr.fields:
            chat_format = "chatml"
            print("note: no chat_template in GGUF -> using chatml", file=sys.stderr)
        del rr
    except Exception as e:
        print("warn: template probe failed:", e, file=sys.stderr)
    llm = Llama(model_path=a.model, n_ctx=a.n_ctx, n_threads=4, n_batch=512, verbose=False, chat_format=chat_format)
    records = []; correct = 0; gen_tokens = 0; gen_time = 0.0
    # Render the chat template ourselves (jinja2, like llama-server's minja) so we control enable_thinking.
    import jinja2, re as _re
    tpl_src = None
    try:
        rr = GGUFReader(a.model)
        if "tokenizer.chat_template" in rr.fields:
            tf = rr.fields["tokenizer.chat_template"]; tpl_src = bytes(tf.parts[tf.data[0]]).decode("utf-8")
        del rr
    except Exception:
        pass
    if not tpl_src:
        tpl_src = ("{% for message in messages %}{{'<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>' + '\n'}}{% endfor %}"
                   "{% if add_generation_prompt %}{{ '<|im_start|>assistant\n' }}{% endif %}")
    jenv = jinja2.Environment(); jtpl = jenv.from_string(tpl_src)
    def render(msgs):
        kw = {"messages": msgs, "add_generation_prompt": True}
        if a.think == "off": kw["enable_thinking"] = False
        elif a.think == "on": kw["enable_thinking"] = True
        try:
            return jtpl.render(**kw)
        except Exception as e:
            print("warn: template render failed, using chatml:", e, file=sys.stderr)
            return "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in msgs) + "<|im_start|>assistant\n"
    def chat(user):
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        prompt = render(msgs)
        t0 = time.time()
        r = llm.create_completion(prompt=prompt, max_tokens=a.max_tokens, temperature=0.0, top_p=1.0, repeat_penalty=1.0)
        dt = time.time() - t0
        txt = r["choices"][0]["text"] or ""
        txt = _re.sub(r"^\s*<think>\s*</think>\s*", "", txt)
        n = r["usage"]["completion_tokens"]
        return txt, n, dt
    for i, row in enumerate(df.itertuples()):
        q = row.question + "\n\nSolve step by step, then give the final numeric answer on its own line as 'Final answer: <number>'."
        txt, n, dt = chat(q)
        gen_tokens += n; gen_time += dt
        pred = last_number(txt); g = gold(row.answer)
        ok = pred is not None and abs(pred - g) < 1e-6
        correct += ok
        records.append({"i": i, "question": row.question, "gold": g, "pred": pred, "ok": bool(ok), "tokens": n, "secs": round(dt, 2), "response": txt})
        print(f"[{i+1}/{a.n}] {'OK ' if ok else 'BAD'} gold={g} pred={pred} ({n} tok, {dt:.1f}s)", file=sys.stderr, flush=True)
    samples = []
    if a.samples:
        for p in TUTOR_PROMPTS:
            txt, n, dt = chat(p)
            samples.append({"prompt": p, "response": txt, "tokens": n, "secs": round(dt, 2)})
    res = {"tag": tag, "model": a.model, "n": a.n, "seed": a.seed, "system_prompt": system, "max_tokens": a.max_tokens,
           "gsm8k_acc": correct / a.n, "correct": correct, "gen_tok_s": gen_tokens / gen_time if gen_time else None,
           "avg_tokens": gen_tokens / a.n, "records": records, "tutor_samples": samples}
    (out_dir / f"{tag}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print("@@EVAL " + json.dumps({k: res[k] for k in ("tag", "n", "gsm8k_acc", "correct", "gen_tok_s", "avg_tokens")}))

if __name__ == "__main__":
    main()
