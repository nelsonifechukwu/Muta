# Offline UI localization

## Outcome

Add a language setting that changes the entire static browser interface immediately, works
without a network connection, survives reloads, and gives African languages first-class
placement. The same setting is the tutor's preferred response language: the browser sends the
BCP 47 tag as request metadata and the gateway adds the preference to the trusted system prompt.
It never rewrites or prefixes the learner's actual message. A translated interface pack still
does not prove tutoring quality in that language, so response quality remains a separately
reviewed model capability.

## Language policy

- Identify locales with BCP 47 tags and show every language by its autonym.
- Do not assign a single national flag to languages that cross borders.
- Group the initial African-language packs before other languages in the selector.
- Every registered language is selectable as the tutor's response-language preference. A locale
  changes the browser interface only when it contains the complete required UI message set;
  otherwise the interface remains English while the selected response preference still applies.
- Initial complete interface tranche: English, Deutsch, Arabic, Kiswahili, and Yoruba. The
  dropdown also includes the 85-language Africa-54 baseline and can accept additional languages
  without changing application code. Country-coverage planning stays in project documentation,
  not in the learner-facing Settings panel.
- Set both `document.documentElement.lang` and `dir`; Arabic is right-to-left.
- Offer `Auto` before the explicit languages. Auto resolves the interface against the best
  complete browser-language pack, but keeps `auto` as the response-language preference so the
  model follows the primary natural language in each latest user message.

## Implementation

1. Add `ui/i18n.js`, loaded before `app.js`, with the locale registry, message catalog,
   interpolation, fallback, persistence, subscription, DOM translation, and testable exports.
2. Annotate authored markup with translation keys for text, placeholders, titles, and ARIA
   labels. Populate the Settings language selector from the registry rather than duplicating
   the language list in HTML.
3. Route runtime-generated interface copy in `app.js` through the same translator, including
   model controls, reasoning controls, statuses, queues, attachment labels, notifications, and
   Send/Stop state. User/model message content and server-provided model names remain untouched.
4. Persist the language preference in browser storage under a versioned key. A saved explicit
   preference controls the next response; its interface uses the matching complete pack or
   English. With Auto, resolve the interface from the supported browser locales, then English.
5. Use CSS logical properties where localization changes direction-sensitive layout; keep the
   present geometry stable in both directions.
6. Send the active locale in `ChatRequest.language` for typed and voice turns. Assemble a
   system-level directive that uses the selected language unless the learner explicitly asks
   for another language for that task, preserves code/variables/commands/URLs/proper nouns, and
   asks for natural rather than literal explanations. Locale changes apply to the next turn in
   an existing conversation; persisted user-message content stays byte-for-byte unchanged.
7. Keep `languagePreference` separate from the resolved interface `locale`. Every explicit choice
   is sent unchanged to the gateway; choices with a complete interface catalog use it, while the
   rest retain English chrome. `auto` follows the browser for interface chrome and is sent
   unchanged to the gateway; the system instruction performs per-turn language selection without
   a language-detection service. If the latest message is too short or ambiguous, continue the
   most recently established response language, then fall back to English.
8. Native deployment discovers every top-level authored HTML, CSS, and JavaScript asset and
   overlays the complete set into `ui/dist` before the gateway starts. Verification follows every
   relative `src` and `href` in `index.html`; a mixed bundle with missing localization scripts is
   rejected instead of serving a non-responsive interface.
9. Context fitting preserves both the trusted system-prefix head and the first per-student block.
   The active language instruction lives at the start of that protected block, so a long English
   conversation cannot truncate the next turn's newly selected response language.
10. Apply the same system-level language assembly to both `/chat*` and `/tutor/chat*` contract
    families. Validate language metadata as bounded BCP 47 before it reaches prompt assembly or
    persistence; no client path may interpolate an unconstrained value into trusted context.

## Verification

- Static tests assert that every complete interface pack has every marked key, every registered
  response language is selectable, and the language selector/runtime load before the application.
- JavaScript tests cover startup resolution, persistence, fallback, interpolation, DOM
  attributes, and right-to-left switching.
- Prompt and route tests prove that the locale lands in the system prompt while the user message
  reaches the inference engine unchanged; static client tests cover typed and voice transports.
- A multi-turn engine test proves that changing an explicit language to Auto replaces only the
  next system instruction while replaying the prior conversation history unchanged.
- A constrained-context regression proves the byte-safe fallback retains both the safety-prefix
  head and a changed response-language instruction at the system prompt's variable tail.
- JSON and streaming tests for both chat route families prove the validated language tag reaches
  the system prompt while the learner's message remains byte-for-byte unchanged.
- Native-export tests prove that newly added UI scripts are discovered, copied, resealed in the
  manifest, and rejected when `index.html` references an absent asset.
- Existing UI and backend tests remain green.
- A fresh-context reviewer probes missing dynamic strings, misleading language claims,
  persistence failures, accessibility regressions, and RTL layout hazards.
