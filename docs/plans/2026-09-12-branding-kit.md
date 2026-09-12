# Muta branding kit

## Authorized result

Build reusable brand assets from the user-approved D / Speaking Dot concept and save them in
the project `branding/` directory. The user approved creation of assets; live product replacement,
deployment, and commits are not part of the request.

## Frozen visual brief

- Natural open book with ivory/terracotta pages and a forest binding; no forced M stems.
- Serif Muta. wordmark with a square-dialogue mark aligned beneath u.
- The square retains its user-explained connection to the Igbo name's pronunciation.
- On standalone icons, repeat the square-dialogue mark below the book.
- Keep the page faces clear. A short tail adds the conversation cue without dominating the square.

## Deliverables

1. Font-free vector masters for stacked logo, horizontal lockup, wordmark, symbol, and dialogue dot.
2. Light, dark, black, and white variants with transparent PNG exports.
3. Opaque app-icon master, rounded avatar previews, optical small icons, favicon PNG/ICO/SVG.
4. Three reusable digital collateral designs: share card, square social card, wide header, plus
   a presentation/title background and branded document-header asset if useful.
5. Color tokens, practical brand guidelines, provenance/source notes, asset manifest, and a local
   preview/download gallery in branding/.
6. Render and inspect representative variants and actual small-size raster outputs. Obtain an
   independent adversarial review and fix material issues before delivery.

## Implementation choices

Redraw the approved raster concept as controlled SVG geometry. Resolve the serif lettering into
paths from an explicitly selected font; document the font and never leave a runtime font fallback
inside logo assets. Keep text editable in collateral source where useful, but render exports
deterministically. Scripts and master sources belong in branding/source/.

## Completed / verification

- Built `branding/` with 70 artwork exports: 20 outlined logo masters and 20 transparent PNGs,
  20 app/avatar/favicon exports, four social/presentation SVG+PNG pairs, and an SVG+PNG brand board.
- Selected Libre Baskerville Regular for the wordmark/display and Instrument Sans Regular/Bold for
  supporting copy; bundled font files and OFL licenses. No live text or external images in exported SVGs.
- Included `index.html`, README, brand guide, CSS/JSON tokens, approved reference and regeneration scripts.
- Independent review corrected monochrome treatment to hollow-left/solid-right, clarified external
  clear space, and routed tiny placements to dedicated optical icons. The 16 px icon omits the tail.
- Final independent visual re-review passed for representative color/mono/minimum-size marks, the
  overview board and all four collateral layouts. No clipping or duplicate speaking dots found.
- `build_manifest.py` verifies SVG structure, local links, PNG transparency/dimensions, opaque app
  masters and exact ICO frame matches. Inventory records file sizes and SHA-256 checksums.
- Browser preview navigation was blocked by the browser URL policy. No alternate browser workaround
  was attempted; visual inspection used local rendered images and the HTML's links were checked statically.
- No production assets, installed icons, application code or git history changed by this kit.
