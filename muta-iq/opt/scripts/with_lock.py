#!/usr/bin/env python3
"""Run a command under an exclusive machine-wide lock so CPU-heavy measurements never overlap.
Usage: with_lock.py [--tag T] -- cmd args...   (blocks until the lock is free; prints wait time to stderr)"""
import fcntl, os, subprocess, sys, time
LOCK = "/private/tmp/claude-501/-Users-timii-Developer-Muta/muta-bench.lock"
args = sys.argv[1:]
tag = ""
if args[:1] == ["--tag"]:
    tag = args[1]; args = args[2:]
if args[:1] == ["--"]:
    args = args[1:]
if not args:
    sys.exit("usage: with_lock.py [--tag T] -- cmd...")
os.makedirs(os.path.dirname(LOCK), exist_ok=True)
t0 = time.time()
with open(LOCK, "w") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    waited = time.time() - t0
    if waited > 1:
        print(f"[with_lock] {tag} waited {waited:.0f}s for the machine lock", file=sys.stderr, flush=True)
    f.write(f"{os.getpid()} {tag} {time.strftime('%H:%M:%S')} {' '.join(args)[:200]}\n"); f.flush()
    rc = subprocess.call(args)
sys.exit(rc)
