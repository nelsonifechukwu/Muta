#!/usr/bin/env bash
# G3 routing sweep + G6/G7 perf matrix for the DUO PoC.
# Usage: bash scripts/bench_duo.sh [outdir]   (default outdir: bench/.runs)
set -u
cd "$(dirname "$0")/.."

DUO=llama.cpp/build/bin/llama-duo
BUNDLE=bundle/muta-duo.gguf
OUT=${1:-bench/.runs}
mkdir -p "$OUT"

TIME="/usr/bin/time -l"   # macOS; on Linux use /usr/bin/time -v and adjust the grep

echo "== G3: routing scores =="
$DUO --bundle $BUNDLE --route-only --prompts-file bench/prompts/easy.txt --no-trace 2>/dev/null > "$OUT/g3-easy.tsv"
$DUO --bundle $BUNDLE --route-only --prompts-file bench/prompts/hard.txt --no-trace 2>/dev/null > "$OUT/g3-hard.tsv"

python3 - "$OUT" <<'EOF'
import sys
out = sys.argv[1]
easy = [float(l.split('\t')[0]) for l in open(f'{out}/g3-easy.tsv')]
hard = [float(l.split('\t')[0]) for l in open(f'{out}/g3-hard.tsv')]
print(f"{'tau':>5} {'easy_ok':>8} {'hard_ok':>8} {'accuracy':>9}")
for tau in (-2, -1, 0, 1, 2):
    e = sum(1 for s in easy if s < tau)
    h = sum(1 for s in hard if s >= tau)
    print(f"{tau:>5} {e:>6}/20 {h:>6}/20 {100*(e+h)/(len(easy)+len(hard)):>8.1f}%")
EOF

run_row () {
    name=$1; shift
    echo "== G6/G7 row: $name =="
    $TIME "$@" > "$OUT/$name.out" 2> "$OUT/$name.err"
    grep -E "^\[turn\]" "$OUT/$name.err" | tail -3
    rss=$(grep "maximum resident set size" "$OUT/$name.err" | awk '{print $1}')
    echo "peak RSS: $((rss / 1024 / 1024)) MiB"
}

EASY_P="What is the capital of Nigeria?"
HARD_P="Solve 3x + 5 = 20 and explain each step."
ESSAY_P="Explain Newton's second law with an example."

run_row router-easy      $DUO --bundle $BUNDLE --mode router -p "$EASY_P"
run_row router-hard      $DUO --bundle $BUNDLE --mode router -p "$HARD_P"
run_row router-escalated $DUO --bundle $BUNDLE --mode router --route-threshold 10 --conf-threshold -0.9 --carry-draft -p "$ESSAY_P"
run_row codraft-f50      $DUO --bundle $BUNDLE --mode codraft -p "$ESSAY_P"
run_row codraft-f25      $DUO --bundle $BUNDLE --mode codraft --seg-min 64 --seg-max 160 --seg-min-expert 16 --seg-max-expert 40 -p "$ESSAY_P"
run_row codraft-f75      $DUO --bundle $BUNDLE --mode codraft --seg-min 12 --seg-max 28 --seg-min-expert 72 --seg-max-expert 160 -p "$ESSAY_P"

echo "== done; raw outputs in $OUT =="
