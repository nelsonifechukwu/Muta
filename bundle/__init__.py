"""Bundle plumbing — the flash-drive artifact and its integrity guarantees (TDD §10, §11).

The bundle is what ships: binaries, models, index, gateway, units. Three invariants live
here, all of them because the target machine is offline, unattended and cheap flash:

1. **Every artifact is hashed twice** — once at the source, once after the copy. Bitrot on
   USB is real (TDD §10.2), and a silently corrupt GGUF fails as gibberish output, not as
   an error.
2. **A mismatch names the file and refuses to start.** Never "integrity check failed".
3. **Nothing is served from USB** (TDD C-4): staging copies to local disk first, because
   first-touch page faults over USB destroy decode latency.

The scripts in `deploy/` are thin wrappers over this package — logic lives in Python so it
is testable; shell stays declarative.
"""
