# M02: two DeepMind generators, source-gap closure

19 September 2026. **Narrow sampler finding independently reviewed by root.**
M02 remains unadmitted. No questions, oracle code, model outputs or dataset
copies were created; no training or evaluator files were changed.

## Bounded plan and evidence identity

Close only the previously inaccessible matrix-sampler dependency, combine it
with the two already-inspected generator entry points and composition mechanism,
then update the feasibility crosswalk without claiming whole-source clearance.

The warehouse's `manifest.json` records a **Git checkout**, not merely a dataset
release: commit `427f45075f84b8b9774950196ad63867ca20ffb3`, tree
`cf56a796d77bdc51810ee292ddf2e76e7818a350`, clean working tree, and overlay
`muta-deepmind-determinism-v1`. The archived registry agrees. Its verified SHA256
is `53dc3f9f93f2ec55ab14cf0b81e71805effd9c600548e0064fa09700c67e1558`;
archived/current adapter and overlay respectively match recorded hashes
`bd50a2c4967c32af7427b1f01de36a4b245cd891b6619b7f36aab68973fd3562` and
`9818f5321b2c3946255cc7d4b45d513da9905c6d1174764be95632498021f98f`.
These are prior build receipts and local file checks, not a rerun of generation.
The source checkout itself is no longer present at its recorded local path.

Root retrieved the single immutable official file after this agent's web tool
returned cache misses. This agent independently read all **144 physical lines**
and rehashed `/tmp/muta-m02-source.JG0Je3/linear_system.py`:

- Source: [pinned sample/linear_system.py](https://raw.githubusercontent.com/google-deepmind/mathematics_dataset/427f45075f84b8b9774950196ad63867ca20ffb3/mathematics_dataset/sample/linear_system.py).
- SHA256: `637d597263bfb2b70831afbf96d11113e79a9d7721b1905b9af38c68d7f362aa`.
- All line references below use the actual file, not the web renderer's
  blank-line-collapsed numbering. The temporary path is not a durable archive.

## Narrow finding

| Physical lines | Observed implementation | Consequence |
|---|---|---|
| 68–85 | `_invertible_matrix` repeatedly samples integer matrices; the exact SymPy determinant must be nonzero at lines 81–82 before it returns | Deliberate singular-matrix rejection, not merely an integer-answer assumption |
| 50–65, 79–80 | Optional `_is_trivial_in` filter rejects an equation isolating the requested variable immediately | Controls triviality; it is separate from the determinant gate |
| 104–112 | `linear_system` obtains that matrix and forms the constant vector as matrix times the supplied solution vector | Intended underlying system has the chosen unique solution |
| 120–144 and 32–47 | Coefficients are split into terms and moved between equation sides | Presentation varies; there is no zero/one/infinite-solution classification target in this sampler |

The already-inspected [pinned algebra entry points](https://raw.githubusercontent.com/google-deepmind/mathematics_dataset/427f45075f84b8b9774950196ad63867ca20ffb3/mathematics_dataset/modules/algebra.py)
map both `linear_2d` variants to `_solve_linear_system` with degree two. They
choose integer solutions and ask for one variable's numeric value. Pure uses
one module; composed uses two to four. The
[pinned composition mechanism](https://raw.githubusercontent.com/google-deepmind/mathematics_dataset/427f45075f84b8b9774950196ad63867ca20ffb3/mathematics_dataset/util/composition.py)
replaces constants with generated entities and checks their values against those
constants. Such handles are not free parameters to classify. The local overlay
changes symbol selection/entity ordering, not the determinant gate or target.

**Inference:** these two named generators intentionally produce determined
numeric solves, not M02's parameter-dependent consistency/rank classification.
This closes their specific unresolved source-code question. M02's proposed
essential singular-case branch is absent from the inspected top-level task
definition; that is not a new-family admission decision.

## Limits and next review gate

The determinant test precedes `astype(int)` at line 84; solution casting and
NumPy multiplication occur at line 111. This static inspection does not prove
absence of fixed-width overflow, dependency/rendering defects, or malformed
historical rows. It did not rerun generators, inspect all composed child modules,
audit every polynomial term-splitting dependency, or replay the build's imported
module provenance. Thus “intended nonsingular construction” is supported;
“every warehouse row is independently verified unique” is not asserted.

Other DeepMind modules/compositions, TemplateGSM, private exam material, old
incumbent inputs and the remaining M02 source/family gates remain unresolved.
Root independently read the full retrieved sampler and checked its exact line
references and SHA256 against the immutable official source. The determinant,
RHS construction and integer-cast limitations above are supported. This review
closes the sampler gap only; it does not expand the earlier entry-point review,
admit M02, verify historical generated rows or clear other corpus families.
