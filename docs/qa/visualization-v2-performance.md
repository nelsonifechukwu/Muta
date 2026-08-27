# Visualization V2 performance and resource evidence

Compared with base revision `238b95ff4e0cd38f2636c25d08e6e1c9eb53ded1` on the local macOS development host.

## Source and startup impact

| Measurement | Before | After | Delta |
|---|---:|---:|---:|
| Synchronous chat UI source | 74628 B | 108207 B | +33579 B |
| Median Node parse time for synchronous JS | 0.5563 ms | 0.7986 ms | +0.2423 ms |
| Lazy V2 renderer source | 0 B | 222947 B | +222947 B |
| Existing vendored visualization libraries | 1102856 B | 1102856 B | 0 B |

The V2 renderer is loaded only inside a validated visualization iframe; ordinary text chat does not fetch it. No CDN or new vendor package was added.

## Real-browser acceptance rendering

The full gate rendered 200 cases. Peak measured browser JS heap across the responsive matrix was 55661813 bytes.
All 105 Three.js cases stayed within their declared GPU triangle budgets; the largest submitted frame contained 26618 triangles.

| Renderer | Cases | Mean first render | p95 | Maximum |
|---|---:|---:|---:|---:|
| svg | 74 | 111.64 ms | 266.00 ms | 350.80 ms |
| canvas | 21 | 171.48 ms | 323.70 ms | 333.40 ms |
| three | 105 | 282.87 ms | 336.70 ms | 710.70 ms |

## Browser screenshots

- `docs/qa/screenshots/coupled-oscillator-modes.png` — 41975 B; SHA-256 `f48352b0e51a340e124d71f726586867f60928d4e4070a38cb4d416761304d38`
- `docs/qa/screenshots/damped-sine-followup-animation.png` — 40157 B; SHA-256 `d4cd6675c0215ffb0c548fd9812c9bb49fe132f656abf613a86dcabbfbfbdb02`
- `docs/qa/screenshots/double-slit-linked.png` — 44580 B; SHA-256 `e19ee0257e198b0a925d1232cea239a7a5072764f3be3e54122f03347708ff69`
- `docs/qa/screenshots/general-vector-field.png` — 42627 B; SHA-256 `49537a08dbb89fdb66f57af0401af0e06d2d8f51449c69502f709253a9e84d78`
- `docs/qa/screenshots/matrix-desktop-dark.png` — 113013 B; SHA-256 `5d3fd3614f9c8353aac5f632ddfb27d8cdc8b492f71d4bde342818e15553b7bc`
- `docs/qa/screenshots/matrix-desktop-light.png` — 112029 B; SHA-256 `233e571e5d89a30c305b6b0413122cbc9f0215531c0a4517abc2435163d5b0d5`
- `docs/qa/screenshots/matrix-landscape.png` — 113136 B; SHA-256 `e84106e75b42722d9cfe053cbc1254504806866cedd5a12535cfd611f9ae2e84`
- `docs/qa/screenshots/matrix-mobile-375.png` — 86611 B; SHA-256 `b75336158da6c8e48cd4f02105fd95df542700204eeb6c84963813e6a3716d43`
- `docs/qa/screenshots/matrix-mobile-430-dark.png` — 96469 B; SHA-256 `714668434f720a03dddb3d55157415523fdc0023c69754d4d27092f9ebe3166f`
- `docs/qa/screenshots/matrix-reduced.png` — 112360 B; SHA-256 `c587a1d76a920025e647b630aed1a93c8ade0cd48b874342ec73e2d3b510539b`
- `docs/qa/screenshots/multipanel-spectrogram-dark.png` — 46479 B; SHA-256 `2e3525737fb0e9021b223e47e8d50749a05dac124cfb76aa7563545c624fb453`
- `docs/qa/screenshots/robot-unreachable.png` — 40072 B; SHA-256 `a3c8f1b7d462b52accc0e8662d2b7de012bfd4c96e5c6468828f9c78ac01c5c2`

## Hard runtime caps

- AST: 160 nodes, depth 24.
- Implicit work: 32768 cells; 32000 triangles.
- Dense 2D: 4096 cells; 800 particles; 4096 declared points.
- Animation: 30 fps, finite duration; active iframe LRU 4.
- LRU browser proof: 6 visualizations, 4 active, 2 suspended; restore kept the cap: true.

## Scope note

Browser JS heap and render timings are measured evidence for this macOS QA run. They are not the competition target's whole-process-tree RSS or thermal result. Target x86 RSS, frame pacing, and thermals must be recorded by the later packaging/target-box task; this task is explicitly prohibited from packaging.

## Reproduce

```bash
.venv/bin/python scripts/visualization_v2_performance.py \
  --browser-results /tmp/muta-v2-browser-results.json \
  --matrix /tmp/matrix-desktop-light.json /tmp/matrix-desktop-dark.json \
            /tmp/matrix-mobile-375.json /tmp/matrix-mobile-430-dark.json \
            /tmp/matrix-landscape.json /tmp/matrix-reduced.json \
  --lru /tmp/muta-v2-lru.json
```
