"""Integration with the official ADTC profiler.

The profiler lives in an isolated venv and is only ever reached by subprocess. It requires
Python >=3.11 (Muta floors at 3.10) and ships GPL-3.0 in LICENSE while its pyproject declares
MIT — so it is never imported into this process and no profiler source enters this tree.
"""

from bench.adtc.install import PROFILER_REPO, PROFILER_SHA, ProfilerUnavailable

__all__ = ["PROFILER_REPO", "PROFILER_SHA", "ProfilerUnavailable"]
