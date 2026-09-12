# Repository cleanup plan — 2026-08-26

## Goal

Remove retired or redundant tracked content without deleting local models, build products,
media sources, test evidence, dependencies, or personal untracked files. Stop before committing
or pushing so the owner can review the exact working-tree changes.

## Inventory conclusions

- `pilot-v2/` is a completed, retired experiment. It is excluded from desktop packaging and
  no current application code imports or executes it. Its complete source remains recoverable
  from Git history beginning at subtree merge `0e543db` and subsequent pilot commits.
- `README2.md` is an obsolete root-level scratch checklist. Its completed TTFT note and open
  benchmark ideas are already represented by the current roadmap, results, and documentation.
- Exact duplicate files under `.agents/skills/`, `landing/`/`ui/`, and
  `muta-iq/opt/patches/`/`results/` are intentional standalone copies or evidence artifacts.
- Ignored model weights, desktop package/build outputs, media production files, virtual
  environments, local databases, and dependency trees are expensive or user-owned working
  data, not repository-cleanup targets.
- The untracked root `NOTE.txt` and screenshot are personal files and remain untouched.

## Changes

1. Remove tracked `pilot-v2/` and `README2.md`.
2. Update current documentation so it no longer links to the removed subtree.
3. Remove ignored `.DS_Store` metadata only; leave all other ignored working data intact.
4. Run reference, status, diff, and repository test checks.
5. Present the exact removals and edits for owner approval. Do not commit or push before that
   approval.
