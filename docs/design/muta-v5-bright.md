# Muta v5 interface — "Bright"

Status: proposed for v5, awaiting product review (2026-10-09). The product owner approved
the direction during review.

## Why the v4 shell had to change

v4's chat shell read as a Claude.ai clone: a warm `#faf9f5` paper page, a neutral sidebar,
terracotta accents, a serif "What are we working on?" headline and serif answer prose. v5
keeps the approved logo artwork untouched and gives the interface its own learning-app
identity.

## References and what they share

The product owner's references were Brilliant, MyTutor, Unibuddy, heyclicky and Opennote.
Opennote has shut down and only shows an announcement page. Studied live, the others share:

- a bright white or warm off-white canvas, with no dark chrome;
- bold, friendly near-black sans headlines and generous space;
- one fresh call-to-action colour (Brilliant green, MyTutor and Unibuddy teal), usually with
  dark text on it;
- playful pastel tints for panels, tiles and decoration (Brilliant's sage and peach panels,
  MyTutor's sun and pink blobs, Unibuddy's lilac);
- pill buttons, white rounded cards and soft shadows; Brilliant marks the selected option
  with a black pill.

A first v5 attempt ("Adire & Loom": an indigo rail, woven-strip motifs and a wide display
face) was rejected in review: it was nothing like the references. Its structural and
bug-fix work was kept; its look was replaced by this one.

## The direction

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg` | `#f7f5f0` | `#181715` | canvas |
| `--card` / `--sidebar` | `#ffffff` / `#fdfcfa` | `#242220` / `#1d1c1a` | surfaces |
| `--text` | `#17181a` | `#f3f0ea` | ink |
| `--muted` | `#5d6066` | `#afa99f` | secondary text |
| `--accent-strong` (Muta mint) | `#3fcfb4` | `#4fd6ba` | action fills, always with `--on-accent` `#0a2b24` text |
| `--accent` | `#0b7a66` | `#6fe0c8` | links and accent text |
| `--selected` | `#17181a` | `#f3f0ea` | the chosen segment (a black pill; white in dark) |
| pastels | sun `#ffd25e`, lilac `#c6b6ff`, peach `#ffb98f`, sky `#9fd2ff`, mint `#8ee3cf` | deeper equivalents | tints mixed at `--tint` (30% light, 9% dark) |
| `--brand` | `#d9573a` | `#ff8a66` | the logo's Muta coral: resource (PDF) icons |

Mint is never used as text on white; text on a pastel or mint fill is always ink.

**Dark mode is warm graphite** (`#181715`), chosen in review over three alternatives, each
rendered in the live app:

| Alternative | Why it lost |
|---|---|
| neutral charcoal `#131416` | colder and flatter |
| cool graphite `#121419` | drifts towards the navy the owner rejected |
| soft charcoal `#1c1d20` | washed out |

Warm graphite is the night twin of the warm light canvas and sits naturally with the logo
(contrast: text 16:1, muted 7.9:1). Green-tinted dark surfaces remain off the table (the
2026-09-12 brand refinement ruled out a forest-green wash).

Yellow and peach turn olive or brown at low luminance, so dark mode keeps tile tints faint
(9%). It moves the colour into bright pastel icon chips, and glows in mint and lilac instead of
sun.

## Logo colourway

The logo's shape and speaking dot are unchanged. Its colours moved to ink, white and **Muta
coral** (`#D9573A`; `#FF8A66` on dark). Terracotta `#AD4F31` read as brown beside the v5
pastels. Coral is mint's near-complement and a stronger version of the peach tint.

Candidates were measured as a tiny speaking dot on the canvas (3:1 is the bar for graphics):

| Candidate | Contrast | Result |
|---|---:|---|
| Muta coral `#D9573A` | 3.6:1 | chosen; 3.9:1 on white |
| Lighter coral `#E8664A` | 3.0:1 | too soft |
| Tangerine | 2.7:1 | fails |
| Marigold | 1.8:1 | fails |
| Violet | 4.0:1 | legible, but cool like mint and the lilac bubbles |

The whole kit is regenerated from `branding/source/build_assets.py`: logos, favicons, app
icon, collateral and gallery. The brand guide records the previous colourway.

## About page (landing)

`landing/` uses the same system: Onest is bundled under `landing/fonts/`, alongside mint pill
actions, coral eyebrow squares and warm-graphite dark.

The interactive lesson band stays a dark stage, recoloured to warm graphite with the app's
pastels, because its maths, story and business labs are drawn for a dark canvas.

The copy comes from the v8 pitch narration:

- Igbo for "learn";
- "too many students are being left behind", with three cited facts, each source printed;
- "learning isn't enough — you must learn correctly";
- adapts when stuck, and checks your working;
- Muta Share, the 22-language interface (interface coverage, not fluent tutoring) and Eco mode;
- a GPT built from scratch and the fine-tuned tutor;
- nursery to career, and the intelligence layer;
- the team;
- the closing line.

Only numbers with a citation in `media/adtc-final/data/citations.json` appear.

**Type.** Onest, an OFL font bundled as a 64 KB subset variable WOFF2 under `ui/fonts/`;
nothing loads from a CDN. Headlines use weight 800 with tight tracking, and body text is 400–650.

Onest was checked glyph by glyph for ẹ ọ ṣ ɓ ɗ ƙ ɛ ɔ ŋ and combining tone marks. The brand's
Instrument Sans fails ɓ ɗ ƙ ẹ ọ ṣ ɛ ɔ, and v4 never loaded it. Onest lacks ₦ and ₵, so those
fall back to the system font. Arabic and Amharic use the system font by design.

**Playfulness.** Two soft, blurred pastel glows sit behind the home welcome, and the Muta mark
sits on a white tile above the headline. Quick-start tiles and course cards are tinted per
subject.

## Information architecture changes

- **Rail:** logo, a full-width mint "+ New chat", then Learn (sun icon tile) and Class (sky)
  above the chat list; v4 buried them at the bottom. "About Muta" and Settings sit in the footer.
- **Home:** a centred welcome plus four pastel quick-starts: photo, voice, Learn and Practice.
  - Each quick-start triggers the existing control (`ui/home.js`); there is no second code path.
  - Photo and voice mirror their control's `disabled` state.
  - Practice opens Learn directly on its Practice tab through `MutaLearning.open("practice")`.
- **Teaching style:** a segmented control beside its label, with the chosen method as a black
  pill.
- **Chat:** student messages are lilac bubbles with one tighter corner (mirrored in RTL); tutor
  answers sit beside a round Muta avatar with full reading width.
- **Learn:**
  - a light header and a segmented tab track;
  - course cards with a pastel band per subject (Maths lilac, Physical science sky, Life
    science mint, History peach, AI sun), always beside the subject's printed name;
  - mint progress bars and pill actions.

## Localization

No English meaning changed. The home quick-starts reuse already-translated keys
(`composer.attachImage`, `voice.talk`) plus the Learn keys, which are English-only in v4 too
(the additive English layer). All 27 interface packs stay release-complete.

## Defects fixed while reviewing every surface

| Defect | Fix |
|---|---|
| The course reader called a non-existent `global.renderMath`, so chapter maths showed raw `$f(x)=2x+1$` (also in v4). | It now uses `MutaMath.render`. |
| Answered game options rendered white text on a pale tint. | They keep ink and show ✓/✗. |
| On first launch, the tour opened on top of the analytics-consent dialog. | It now waits until consent is answered. |
| The tour card clamped itself with a hard-coded 380×250 px size. | It measures itself, so longer languages stay on screen. |
| `--line`, `--ink` and `--panel` were referenced but undefined. | They are now aliases. |

An adversarial review also caught and fixed the following:

- the Practice quick-start landing on Library;
- the tour card losing `position: fixed`;
- the phone header losing its safe-area inset;
- the 375 px composer fit;
- focus returning into the closed phone drawer;
- RTL blockquote corners.

## Review refinements (2026-10-09)

**The Muta tile.** The mark appears in-app as one treatment: a rounded square with a card fill
and a soft shadow. Three sizes share the same corner ratio:

| Placement | Size | Radius |
|---|---|---|
| home welcome | 64 px | 20 px |
| sidebar | 44 px | 14 px |
| chat avatar | 32 px | 10 px |

The avatar was previously a circle, and the sidebar mark sat bare. The wordmark and stacked
logo remain the standalone variants, used on the splash, LAN sign-in and About page. The native
app icon is the app-icon variant.

**Teaching method.**
- The header pill repeated the active method already shown as the black pill in the teaching
  control. It is now visually hidden but kept as the polite live region that announces style
  changes to screen readers.
- The method name (for example "Worked-example method") sits directly under "How should Muta
  teach?" as the control's subtitle.
- "?" opens the method's description as a note attached beneath the control.

## Brand-consistency audit (2026-10-09)

Every surface was walked in the live app in light and dark, and a static sweep covered every
stylesheet and script. All of the following were fixed.

**Type**
- Many buttons and inputs rendered in Arial 13.3px, because form controls don't inherit the
  page font by default and three `font:` shorthands were invalid. They now inherit Onest.
- The remaining v4-weight headings were moved to the v5 type scale:
  - class board;
  - host course form;
  - legacy unit modal.

**Labels**
- Small uppercase labels are coral, each with a speaking-dot square, matching the About page:
  - Learn kicker;
  - consent eyebrow;
  - LAN sign-in eyebrow;
  - tour step counter;
  - practice and infographic meta.
- A text-safe `--brand-text` token (`#b8462c`, 4.9:1) carries them.

**Controls**
- Tour Skip and Back were raw browser buttons. They are now warm-grey pills.
- All secondary actions are pills:
  - "Continue answer";
  - class-board buttons;
  - the "ask the class" fallback buttons;
  - the startup retry button.
- The LAN sign-in switch moved from a mint track to the shared warm-grey `--chip` track.
- Stop is neutral: the selected-pill ink (`--selected`, off-white in dark mode) with the
  `--on-selected` square, never mint on hover. Red is reserved for destructive or live states —
  the recording mic and Delete — following platform guidance that red marks destructive actions.
- Mint fills always carry `--on-accent`, and red fills `--on-danger`. The source rules were
  fixed, not only overridden.
- The PDF badge glyph gets ink on dark mode's lighter coral.

**Visualizations**
- **Palette and type:** the sandboxed visualization frames used the v4 palette (terracotta
  first) and Inter. They now use:
  - v5 hues deepened to stay legible as lines and labels (3.6:1 or better on white, 6.4:1 or
    better on dark);
  - Onest, bundled same-origin. `font-src 'self'` now matches the desktop gateway's header
    in the frame meta tag and in nginx.
- **Named colours:** course diagrams name colours in words. Raw CSS keywords such as "teal"
  and "purple" produced harsh fills with white labels. Words now map to the brand slots.
- **Nodes and links:**
  - nodes are pastel tints, computed in JS because the frame's CSP forbids inline styles,
    with a brand-hue outline and ink labels;
  - links stop at box edges instead of crossing the labels;
  - link captions are lighter;
  - the SVG view widens to fit nodes that courses placed past the 720-unit canvas (six nodes
    across three courses had been clipped).
- **Geometry colour:** axes and grids keep a strong colour (dark 8.5:1, enforced by a test).
  Container edges use a separate subtle `--viz-edge`.

**Smaller fixes**
- Correctness and course links use the accent instead of the browser's default blue.
- Knowledge-graph, mastery and reasoning-menu states use mint and the neutral chip.
- The dark-mode splash error box has a dark variant.
- The landing check badge is mint with ink.
- The shipped bundles no longer carry the unused Instrument Sans and Libre Baskerville files
  (about 284 KB each). They stay in `branding/fonts` for regenerating the outlined artwork.

## Tour and preferences forgotten on every launch (fixed)

The desktop shell used to start the gateway on a random port each launch (`available_port()` in
`desktop/src-tauri/src/main.rs`). The web view keeps storage per origin, so each launch was a new
origin and forgot:

- the finished tour;
- the appearance choice;
- composer drafts.

This affected v4 too.

The gateway now prefers a stable loopback port, `PREFERRED_GATEWAY_PORT = 46871`, which
`MUTA_DESKTOP_GATEWAY_PORT` overrides. It falls back to a random free port only when that one is
taken; that launch then starts with empty storage, as before. The engine port stays random.

Verification: Rust unit tests cover both the free and the taken case. On macOS, a relaunch reused
46871 and the tour did not return.

## Rejected alternatives

- **Re-tinting the v4 layout.** It would remain recognisably Claude.
- **"Adire & Loom"** (indigo rail and woven-strip motifs). Rejected in review as unlike the
  references.
- **A sans-serif redraw of the wordmark.** Offered; the owner kept the approved shapes and only
  asked whether the colours fit.
- **A wide display face (Unbounded).** Too loud next to the references' friendly sans.
- **New English home copy.** It would need reviewed overrides in 26 locales, or English
  fallbacks would regress the localized home screen.
