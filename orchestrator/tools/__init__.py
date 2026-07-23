"""Deterministic tools — the parts of the answer that must not be probabilistic (TDD §7.5).

A tutor that computes is a tutor that can be wrong confidently. SymPy decides equivalence,
Matplotlib draws the diagram, and the model only ever *proposes* — which is why both run
behind a sandbox with hard limits: a tool that hangs or leaks takes the 7 GiB budget with
it, and an OOM kill is a disqualification rather than a wrong answer.
"""
