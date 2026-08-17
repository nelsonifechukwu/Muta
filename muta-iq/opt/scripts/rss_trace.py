#!/usr/bin/env python3
"""Run cmd, sample child RSS every 20 ms, print samples above a threshold with wallclock ms (steady_clock-comparable via time.monotonic)."""
import subprocess, sys, threading, time, psutil, os
cmd = sys.argv[1:]
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=open("/tmp/muta_trace_stderr.txt","w"))
p = psutil.Process(proc.pid)
samples=[]
while proc.poll() is None:
    try: samples.append((time.monotonic()*1000, p.memory_info().rss/2**20))
    except Exception: break
    time.sleep(0.02)
mx = max(samples, key=lambda x:x[1])
print(f"peak {mx[1]:.0f} MB at t={mx[0]:.0f}; n={len(samples)}")
big=[(round(t),round(m)) for t,m in samples if m>700]
print("samples >700MB:", big[:40], "..." if len(big)>40 else "")
open("/tmp/muta_trace_samples.txt","w").write("\n".join(f"{t:.0f} {m:.0f}" for t,m in samples))
