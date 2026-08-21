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
- A selectable locale must contain the complete required UI message set. An incomplete locale
  falls back per-message to English during development and must not be presented as complete.
- Initial complete tranche: English, Deutsch, Arabic, Kiswahili, and Yoruba. The draft Africa-54
  baseline maps 85 candidate written-language packs across all 54 countries in a separate,
  accessible country-coverage disclosure; the selector contains only complete packs. Additional
  languages follow that baseline and can be added without changing application code.
- Set both `document.documentElement.lang` and `dir`; Arabic is right-to-left.

## Implementation

1. Add `ui/i18n.js`, loaded before `app.js`, with the locale registry, message catalog,
   interpolation, fallback, persistence, subscription, DOM translation, and testable exports.
2. Annotate authored markup with translation keys for text, placeholders, titles, and ARIA
   labels. Populate the Settings language selector from the registry rather than duplicating
   the language list in HTML.
3. Route runtime-generated interface copy in `app.js` through the same translator, including
   model controls, reasoning controls, statuses, queues, attachment labels, notifications, and
   Send/Stop state. User/model message content and server-provided model names remain untouched.
4. Persist the locale in browser storage under a versioned key. Resolve startup locale in this
   order: saved selection, supported browser locale, English.
5. Use CSS logical properties where localization changes direction-sensitive layout; keep the
   present geometry stable in both directions.
6. Send the active locale in `ChatRequest.language` for typed and voice turns. Assemble a
   system-level directive that uses the selected language unless the learner explicitly asks
   for another language for that task, preserves code/variables/commands/URLs/proper nouns, and
   asks for natural rather than literal explanations. Locale changes apply to the next turn in
   an existing conversation; persisted user-message content stays byte-for-byte unchanged.

## Verification

- Static tests assert that every marked key exists in every selectable locale and that the
  language selector/runtime are wired before the main application.
- JavaScript tests cover startup resolution, persistence, fallback, interpolation, DOM
  attributes, and right-to-left switching.
- Prompt and route tests prove that the locale lands in the system prompt while the user message
  reaches the inference engine unchanged; static client tests cover typed and voice transports.
- Existing UI and backend tests remain green.
- A fresh-context reviewer probes missing dynamic strings, misleading language claims,
  persistence failures, accessibility regressions, and RTL layout hazards.
