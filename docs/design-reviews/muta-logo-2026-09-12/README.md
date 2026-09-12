# Muta logo system — review set

Status: concept review only. No production asset has been changed.

## Production blocker: clear the name first

A quick landscape check found an existing African-language learning platform at
[muta.co](https://muta.co/) offering lessons, tutors, progress tracking, and offline learning.
There is also an unrelated [Muta utility app](https://apps.apple.com/ca/app/muta/id1594081135).
This is not a legal conclusion, but it is a material same-category naming risk. Do not roll out a
new identity until counsel or a qualified trademark practitioner has completed jurisdiction-specific
word-mark and device-mark clearance.

## Conditional design recommendation

Adopt **Direction A — The Foothold** for refinement and implementation.

The mark is a single asymmetric open `u` above one terracotta square. The `u` carries the name;
the square is the learner's first sound idea—the foothold from which Muta helps build the next
step. The square is explicitly a foundation, not a second punctuation mark; the terminal full stop
remains part of the existing editorial wordmark.

It is intentionally not a book, speech bubble, cube, brain, spark, or robot. Those symbols explain
the category but rarely identify the brand. The Foothold uses two shapes, survives one-color use,
and is legible as a 16 px favicon.

## Reference critique

The supplied Gemini concept has a warm, credible palette and correctly connects the terracotta
detail to the `u`. Its open-book + chat + cube stack is too descriptive, however: it combines three
common edtech/AI metaphors, creates fine details that disappear below 48 px, and gives the app icon
a different visual centre from the wordmark. The cube also makes the existing square feel like a
technology ornament instead of a learning idea.

## Directions compared

This is a qualitative design comparison, not a trademark or consumer-recognition study. Precise
numeric scores were deliberately removed after adversarial review because the non-selected routes
have not received the same full production-variant treatment.

| Direction | Distinctiveness hypothesis | Simplicity | Small-size outlook | Accessibility | Existing-brand fit |
|---|---|---|---|---|---|
| A — The Foothold | Strongest: name-linked asymmetric `u`, but needs formal similarity testing | Excellent | Verified at 16/24/32 px | Strong | Excellent |
| B — Stepline | Medium: rising tiles are common in analytics/finance | Excellent | Strong hypothesis; not fully exported | Strong | Good |
| C — Common Ground | Medium: may resemble focus/capture UI | Good | Good hypothesis; not fully exported | Strong | Good |
| Supplied reference | Low: book + chat + cube are common category signals | Low | Weak below 48 px | Adequate | Good palette fit |

Direction B is exceptionally compact, but the rising-block motif is common in analytics and
finance. Direction C expresses tutoring well, but risks reading as focus/capture UI. Direction A
is the strongest design hypothesis because it is simultaneously name-linked, system-linked, and
category-independent. It is not approved for rollout until the naming and similarity checks above.

## Recommended system

### Form hierarchy

- **Primary:** wordmark-only `Muta.` with the terracotta foothold centred under the `u`; use in
  navigation, editorial covers, and any context where the name must lead.
- **Horizontal lockup:** standalone mark + unmodified wordmark; use for launch screens and wider
  partner/press contexts. Do not add a second foothold beneath the `u` in this lockup.
- **Standalone mark:** open `u` + foothold, with no enclosing shape.
- **Application icon master:** full-bleed, opaque forest field; platform masks are applied downstream.
- **Rounded app-icon previews:** review mockups only, never platform source masters.
- **Small-size mark:** optically simplified `u` with a proportionally larger foothold at 16–32 px.
- **Monochrome:** both elements become one color; never remove the foothold.

### Palette

| Token | Hex | Role |
|---|---|---|
| Muta forest | `#1D251F` | Core mark, app-icon ground, dark brand surface |
| Muta ink | `#302D24` | Wordmark on light surfaces |
| Muta ivory | `#F5F1E7` | Reversed mark, warm icon foreground |
| Muta paper | `#FAF9F5` | Light brand surface |
| Muta terracotta | `#AD4F31` | Foothold on light surfaces |
| Muta terracotta light | `#E58C69` | Foothold on forest/dark surfaces |

Key contrast checks: forest/ivory 13.93:1; forest/paper 14.91:1; terracotta/paper 5.06:1;
terracotta-light/forest 6.20:1. The mark does not rely on color alone: silhouette and placement
remain intact in monochrome.

### Typography shown in this review

- **Logo source:** Iowan Old Style Bold 700, matching the repository's current editorial family and
  the actual font used to render these boards. Convert the approved wordmark to outlines before
  shipping so the logo has no runtime font dependency. Customise only the `u` spacing and full stop.
- **Brand/display companion:** Iowan Old Style 600/700; Baskerville is the review fallback only.
- **Interface/body companion:** Inter 400/500/600, already consistent with the product UI. For a
  future accessibility-led type pass, test Atkinson Hyperlegible Next separately; it is not part of
  this logo approval.

The review SVGs keep one kerned live-text node so spacing remains editable. They are concept sources,
not final shipping wordmarks. The standalone/app marks are font-free vectors. An implementation
pass must outline the approved wordmark and run platform-specific asset generation.

## Construction

Use a 512-unit master grid.

- Core `u` centreline: x = 150 and 362; left top y = 164; right top y = 112; curved base centred
  at x = 256. The unequal shoulders make it a lowercase `u`, echo the wordmark, and avoid a
  generic capital-U monogram.
- Core stroke: 64 units, square caps, round joins.
- Foothold: 48 × 48 units at x = 232, y = 404; 4-unit corner radius.
- Gap between the curved `u` silhouette and foothold: optically 18–22 units.
- Full-bleed app master: 512 × 512 opaque square; rounded tiles in this set are previews only.
- Never rotate, bevel, extrude, shadow, or turn the foothold into a cube.

For 16–32 px, use the optical favicon master rather than mechanically shrinking the 512 grid:
the `u` stroke is 4.5 units on a 32-unit grid and the foothold is 4 × 4 units.

## Clear space and minimum sizes

Define **x** as the foothold's width.

- Standalone mark/app icon: clear space ≥ 1x on every side.
- Wordmark: clear space ≥ 1x above and left/right; ≥ 1.5x below so the foothold never feels cropped.
- Primary wordmark minimum: 96 px wide digital / 24 mm print.
- Standalone mark minimum: 24 px for ordinary UI; use the supplied optical favicon at 16 px.
- App icon artwork: author at 512 px or larger; platform masks are applied outside the full-bleed
  master. The set includes separate Android adaptive background, foreground, and monochrome layers.

## Background rules

- Paper/white: forest or ink wordmark with `#AD4F31` foothold.
- Forest/near-black: ivory wordmark with `#E58C69` foothold.
- Busy imagery: use a solid forest or paper holding shape; do not add outlines or shadows.
- One-color reproduction: use the complete monochrome asset, including the foothold.

## Output and print notes

- Raster previews are exported in the standard sRGB web color space.
- SVG files retain the hexadecimal sRGB palette above and are the review masters.
- For print, use the positive or reverse one-color artwork when production conditions are unknown.
  Any CMYK or spot-color conversion must be proofed with the selected printer and stock; this review
  deliberately does not prescribe untested conversion values.

## Files

- `boards/00-overview.svg|png` — side-by-side concept comparison.
- `boards/01-foothold.svg|png` — recommended system and small-size tests.
- `boards/02-stepline.svg|png` — alternative direction.
- `boards/03-common-ground.svg|png` — alternative direction.
- `boards/04-usage.svg|png` — clear space, minimum size, and color use.
- `recommended/` — review SVG variants, complete one-color lockups, an opaque app master, Android
  adaptive layers, rounded previews, and rendered 16/24/32 px PNG favicons.
- `asset-manifest.json` — machine-readable asset roles, palette, and type recommendations.
- `concepts/` — vector sources for the two non-selected routes.
- `process/ai-symbol-exploration.png` — generated ideation sheet retained for process transparency;
  it is not approved art and did not supply final vector geometry.
- `process/reference-gemini-concept.png` — the supplied concept retained beside the critique so the
  comparison remains inspectable.

## Approval boundary

Approval of this review set should first resolve the name-clearance blocker, then choose one design
direction and authorise a separate implementation pass. That pass would outline the approved
wordmark, replace production assets, regenerate platform icon derivatives, update tests, and build
packages only if explicitly requested.
