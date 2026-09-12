# Muta brand guide

This kit develops the selected open-book and speaking-dot identity into reusable artwork. Its approved masters are the source of truth for the product interface, installed app icon, browser icon, landing page and branded companion surfaces.

## The identity

The book is a natural open book: two clear pages, a central fold and a curved cover beneath them. Its silhouette can quietly suggest an M, but it should read as a book without anyone needing that explanation. The ivory and terracotta pages give it warmth; the forest cover gives it definition.

The square beneath the `u` matters. The user explained that it carries pronunciation significance in the Igbo name, so its relationship to the `u` is preserved. A small attached tail adds a second reading: conversation with a tutor. The square body remains the dominant shape. This guide records the intended brand treatment; it does not prescribe an exact Igbo spelling or make a linguistic claim about the square's shape.

The terminal full stop in **Muta.** is separate from the speaking dot beneath the `u`. Keep both in the supplied wordmark. When writing about the product in running text, write **Muta** normally.

## Choose the right asset

| Asset | Use |
|---|---|
| Stacked logo | Covers, posters, title pages and generous vertical spaces. |
| Horizontal logo | Headers, document mastheads and wide layouts. |
| Wordmark | Compact places where the product name is more useful than the book. |
| Standalone symbol | Avatars, app surfaces and places where the name is already known. |
| Speaking dot | A supporting motif in materials that already identify Muta. It is not the primary identifier by itself. |
| Optical favicon | Browser tabs and other 16–32 px placements. |

In a combined logo, the book has no dot of its own: the single speaking dot sits beneath the wordmark's `u`. In the standalone symbol, the speaking dot sits beneath the book's central fold. Do not put a second speech bubble inside the pages or duplicate the dot in one combined logo.

Every logo arrangement is supplied in four treatments:

| Suffix | Background and appearance |
|---|---|
| `on-light` | Forest/ink, ivory and terracotta artwork for paper, ivory or white backgrounds. |
| `on-dark` | Ivory and lighter terracotta artwork for forest or similarly dark backgrounds. |
| `black` | Single-color black artwork for light backgrounds and single-ink work. |
| `white` | Single-color white artwork for dark backgrounds and reversed work. |

Logo SVGs and PNGs have transparent surroundings. White artwork may appear blank on a white preview. The app master includes an opaque forest background; avatar previews include their indicated backgrounds.

## Spacing and size

Use **x** for the width of the speaking dot's square body, excluding its tail. Leave at least **2x** clear space around complete stacked, horizontal and wordmark logos. Measure from the visible artwork, not just the text baseline. Never let the tail approach another object or a crop edge by less than **1x**. Standalone symbols need at least **1x** clear space around their outermost visible shape.

The exported canvases are compact and do not include all of this clear space. Add the required spacing in the surrounding layout; the file's transparent margin alone is not the spacing specification.

These are recommended minimum display widths for this kit:

| Form | Minimum width |
|---|---:|
| Wordmark | 120 px |
| Stacked or horizontal logo | 200 px |
| Standalone symbol | 48 px |
| Dedicated optical favicon | 16 px |

Use the dedicated favicon artwork at 32 px and below. Prefer it throughout the 16–64 px range whenever the full book's fine contour looks weak. Its simplified curves, gaps and speaking dot are adjusted for small pixels; shrinking a large logo is not equivalent. The 16 px version deliberately omits the speech tail and binding, keeping the two pages and separate square crisp.

Preserve the aspect ratio. Do not crop the pages or tail, move the square away from the `u`, rotate the logo, add a shadow, fill the pages with content, or introduce extra outlines. Put the artwork on a quiet area of a photograph or add a solid brand-colored panel behind it.

## Color

| Color | Hex | RGB | Role |
|---|---|---|---|
| Forest | `#1D251F` | 29, 37, 31 | Dark surfaces, book cover, primary brand field. |
| Ink | `#171C18` | 23, 28, 24 | Wordmark and text on light surfaces. |
| Ivory | `#F5F1E7` | 245, 241, 231 | Light page and reversed artwork. |
| Paper | `#FAF9F5` | 250, 249, 245 | Main light background. |
| Terracotta | `#AD4F31` | 173, 79, 49 | Page and speaking dot on light surfaces. |
| Terracotta light | `#E58C69` | 229, 140, 105 | Page and speaking dot on dark surfaces. |

Use the lighter terracotta on forest to preserve the small mark's visibility. Keep the page colors flat. Gradients, textures and highlights in earlier concept images are not part of these vector masters.

[tokens.json](tokens.json) and [tokens.css](tokens.css) hold the reusable color values. Treat this brand palette as a starting point for product styling, not a complete set of UI state colors. Check text and control contrast in the actual interface, and do not use color alone to communicate feedback.

## Typography

**Libre Baskerville Regular** provides the wordmark's letterforms and display typography. **Instrument Sans Regular and Bold** provide supporting copy, labels and emphasis. All lettering in the exported logo and collateral SVGs is converted to paths, so those assets need no installed fonts. The gallery uses the bundled fonts locally and works offline.

| Font | Files | License |
|---|---|---|
| Libre Baskerville Regular | [TTF](fonts/LibreBaskerville-Regular.ttf) | [OFL](fonts/LibreBaskerville-OFL.txt) |
| Instrument Sans Regular | [TTF](fonts/InstrumentSans-Regular.ttf) | [OFL](fonts/InstrumentSans-OFL.txt) |
| Instrument Sans Bold | [TTF](fonts/InstrumentSans-Bold.ttf) | [OFL](fonts/InstrumentSans-OFL.txt) |

Preserve the OFL licenses whenever redistributing the font files. Use local font files for live text in new materials that must work offline.

Keep display headings short and comfortably spaced. Use the sans serif for explanations, controls and captions. In ordinary interface or document copy, begin around 16–18 px with a line height near 1.5; do not copy the logo's tight display spacing into body text.

Do not rebuild the logo by typing “Muta.” in a similar font. Use the supplied artwork so the letter spacing, square placement and tail stay consistent.

## Supporting materials

The social and presentation assets reuse the same logo geometry and palette. Their layouts leave space for the mark to breathe and keep book pages free of decorative content. Use the supplied landscape share card, square graphic, wide header and title background as starting points; adapt copy to the audience without inventing product claims.

Muta's voice is clear, patient and curious. Prefer concrete language about learning and understanding. A useful short descriptor is **“Offline-first AI tutor for maths & science.”** Avoid promises of guaranteed grades, complete correctness or features not present in the product.

## Digital, print and source files

SVG is the preferred source for layout and export. Its curves and outlined lettering remain sharp at any scale. PNG is a convenient fallback for systems that do not accept SVG. The app master is square and opaque; platform packaging or masking remains a separate integration step.

The supplied vector colors are RGB and raster exports are intended for screen use. For print, give the printer the vector artwork and agree on a proof using the actual paper and process. CMYK conversions and spot-color matches can shift ivory and terracotta, so this kit does not invent untested print values. Use the single-color artwork when a single ink, engraving or embossing is required.

The vector artwork is a clean optical redraw of the [approved concept](reference/approved-concept.png), with controlled curves, outlined typography and consistent colors. The concept image and its prompts remain in the [design exploration](../docs/design-reviews/muta-book-m-sweep-2026-09-12/).

Edit the build sources, regenerate the outputs and inspect the gallery after any geometry or typography change. Keep changes to letterforms, dot placement and icon proportions synchronized across the variants. [manifest.json](manifest.json) inventories the delivered files.
