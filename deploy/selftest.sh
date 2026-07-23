#!/usr/bin/env bash
# Clean-room self test (TDD T16, §11.4, S10) — the rehearsal for a judge's laptop.
#
#   deploy/selftest.sh [--root /opt/tutor] [--profile classroom|solo-demo] [--offline-only]
#
# Designed to run inside `docker run --network none --memory 8g ubuntu:24.04`: everything it
# needs must already be in the bundle. A green run means the bundle boots, verifies, answers
# one text question and renders one diagram with no network and no install step.
set -euo pipefail

ROOT="${TUTOR_ROOT:-/opt/tutor}"
PROFILE=classroom
OFFLINE_ONLY=0
FAIL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --offline-only) OFFLINE_ONLY=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

step() { printf '\n== %s\n' "$1"; }
ok()   { printf '   PASS  %s\n' "$1"; }
bad()  { printf '   FAIL  %s\n' "$1"; FAIL=1; }

step "bundle integrity (TDD §10.2)"
if python3 -m bundle.manifest verify --root "$ROOT"; then ok "manifest"; else bad "manifest"; fi

step "engine ISA (TDD C-1 — an illegal instruction is a disqualification, not a deduction)"
BIN="$ROOT/bin/llama-server-core"
if [ -x "$BIN" ]; then
  if file "$BIN" | grep -q 'x86-64'; then ok "x86-64 ELF"; else bad "not x86-64 ELF"; fi
  if objdump -d "$BIN" 2>/dev/null | grep -qE '\s(vpxord|vpternlogd|kmovw)\s'; then
    bad "AVX-512 mnemonics present"
  else
    ok "no AVX-512"
  fi
else
  bad "engine binary missing at $BIN"
fi

step "no network (TDD §2 C-4)"
if [ "$OFFLINE_ONLY" = "1" ]; then
  if curl -s --max-time 3 https://example.com >/dev/null 2>&1; then
    bad "network reachable — this is not a clean-room run"
  else
    ok "network unreachable, as required"
  fi
fi

step "serving profile resolves (TDD §6.2)"
if PROFILE="$PROFILE" TUTOR_ROOT="$ROOT" python3 -m runtime.profiles print core --profile "$PROFILE" >/tmp/core.cmd; then
  ok "core invocation: $(wc -w </tmp/core.cmd) tokens"
else
  bad "profile did not resolve"
fi

step "services up"
for probe in "core:${TUTOR_CORE_PORT:-8081}" "gateway:${TUTOR_GATEWAY_PORT:-8080}"; do
  name="${probe%%:*}"; port="${probe##*:}"
  if curl -fsS --max-time 5 "http://127.0.0.1:$port/health" >/dev/null 2>&1 \
     || curl -fsS --max-time 5 "http://127.0.0.1:$port/v1/health" >/dev/null 2>&1; then
    ok "$name responds on :$port"
  else
    bad "$name not responding on :$port"
  fi
done

step "canned S1 (text turn) + S5 (diagram)"
python3 - "$ROOT" <<'PY' || FAIL=1
import json, sys, urllib.error, urllib.request

def post(path, body, timeout=120):
    req = urllib.request.Request(
        f"http://127.0.0.1:8080{path}",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

try:
    reply = post("/v1/chat", {"student_id": "selftest", "message": "What is 12 x 12?"})
    assert reply.get("reply"), "empty reply"
    print("   PASS  S1 text turn")
except Exception as e:  # noqa: BLE001 — the selftest reports, it does not raise
    print(f"   FAIL  S1 text turn: {e}")
    sys.exit(1)

try:
    svg = post("/v1/tutor/render", {"kind": "matplotlib", "code": "ax.plot([0,1],[0,1])"})
    assert svg.get("svg", "").lstrip().startswith("<"), "not an SVG"
    print("   PASS  S5 diagram render")
except Exception as e:  # noqa: BLE001
    print(f"   FAIL  S5 diagram render: {e}")
    sys.exit(1)
PY

printf '\n== result: %s\n' "$([ "$FAIL" = 0 ] && echo GREEN || echo RED)"
exit "$FAIL"
