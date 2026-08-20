# UI equation rendering repair

## Failure

Assistant replies pass through `marked.parse()` before KaTeX auto-rendering. CommonMark treats
the backslashes in `\[` / `\]` and `\(` / `\)` as punctuation escapes, so the delimiters are
already reduced to literal square brackets or parentheses by the time KaTeX inspects the DOM.
That is the raw output visible in the mitosis screenshot. The same path is used for streaming,
finalized, failed-partial, and restored-history replies, so the defect is cross-cutting.

## Changes

1. Move math-aware rendering into a small `ui/math.js` module used by every assistant reply.
2. Extract complete TeX spans before Markdown parsing, replace them with inert private-use
   placeholders, sanitize the Markdown HTML, restore the original TeX as text, and only then
   invoke KaTeX only for the restored math slots. This keeps Markdown from consuming delimiters
   or interpreting TeX underscores, asterisks, and angle brackets, and prevents KaTeX from
   mistaking ordinary prices such as `$20 and $30` for equations.
3. Support inline/display dollar delimiters, `\(...\)`, `\[...\]`, and the common KaTeX AMS
   environments emitted by local models. Exclude fenced, inline-backtick, raw HTML code/literal
   elements, and comments before matching math. Treat indented regions as non-crossable soft
   boundaries while still allowing complete formulas nested under list items. Keep malformed or
   incomplete streaming TeX visible until its closing delimiter arrives.
4. Make rendering fail soft when an offline vendor asset is unavailable: sanitized Markdown (or
   plain text) remains readable instead of throwing and blanking a reply.
5. Give display equations bounded horizontal scrolling, usable vertical spacing, and mobile-safe
   sizing without widening the conversation column.
6. Add pure extraction tests, static asset/export assertions (including upgrade from a legacy
   native bundle), browser checks for the screenshot formats, and a security regression proving
   model HTML stays sanitized.

## Verification

- Run Node syntax and math extraction tests plus the focused UI/export suites.
- Render representative algebra, fractions, text commands, lists, headings, currency, code
  fences, malformed streaming TeX, and wide display equations in a production-asset browser.
- Run the full test suite and a fresh adversarial review.
- Commit once, push GitHub, and synchronize the GCP checkout to the identical revision without
  deleting its untracked benchmark artifacts.
