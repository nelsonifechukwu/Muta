# Fix sherpa-onnx audio initialization crash

## Failure

`uv run pytest -q` exits with signal 11 while collecting
`orchestrator/tests/test_audio_service.py`. Importing `orchestrator.audio.service` creates the
module-level FastAPI app, `create_app()` eagerly calls `load_engines()`, and `SherpaAsr`
enters native `OfflineRecognizer.from_moonshine()` before pytest can inject fake engines.

The local environment also has an invalid split-package installation: the Python wrapper is
`sherpa-onnx 1.13.8`, while its native `sherpa-onnx-core` is `1.13.6`. `uv pip check` reports
the incompatibility. A native ABI mismatch can segfault and cannot be caught with Python
`try`/`except`.

## Changes

1. Move real engine construction into the FastAPI lifespan so importing the service is safe.
   Explicit fake/null engines continue to work in unit tests without touching native code.
2. Add a version guard before loading sherpa native engines. A wrapper/core mismatch degrades
   to the honest null engine instead of entering incompatible native code.
3. Pin matching `sherpa-onnx` and `sherpa-onnx-core` versions in the Python and container
   dependency surfaces.
4. Add regression tests proving module import does not load real engines and mismatched split
   packages are rejected before recognizer construction.

## Verification

- Repair the local virtual environment to matching sherpa packages and run its Moonshine smoke
  test in a subprocess.
- Run audio engine/service tests.
- Run the complete test suite and lint the changed files.
- Confirm `uv pip check` reports no dependency mismatch.
