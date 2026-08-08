# Privacy and data flows

**Audience:** the school or NGO operator deploying Muta, and any data-protection reviewer
assessing it.

**Scope:** this describes the system *as the code stands today* (the 3-container stack on
`main`). It is a factual map of what data is collected, where it lives, and what — under
specific configurations — leaves the device. It also lists the known gaps honestly: this
doubles as a known-issues document. It is **not legal advice**; the regulatory section is
"what an operator must consider," not a compliance sign-off.

> **The students are minors.** Muta is built for African secondary-school students.
> Everything below is therefore *children's personal data*, which every framework named
> here treats as a special category with a higher bar for lawful processing and consent.

---

## 1. What is collected and where it lives

All persistent student data is in **one Postgres database**, in the Docker named volume
**`muta-pgdata`** (`docker-compose.yml:16-17`, `131-132`). There is no other datastore.
The schema is defined in `runtime/memory.py:25-62`:

| Table | What it holds | Sensitivity |
|---|---|---|
| `conversations` | one row per chat thread: `student_id`, `mode`, `persona`, `subject`, `language`, `title` (the first message truncated to 80 chars — `routes.py:154`, `:217`), `created_at`/`updated_at` | identifies a student and the topics they struggle with |
| `messages` | the full text of **every** student message and every assistant reply (`role`, `content`, `created_at`) | the child's own words, questions, mistakes |
| `attachments` | raw bytes (`BYTEA`) of uploaded images and audio — photos of handwritten work (`routes.py:570-576`) and recorded/uploaded audio; plus `kind`, `mime`, `created_at` | images may show a child's handwriting, name, or surroundings; audio is their voice |
| `user_settings` | one JSONB blob per `student_id` | preferences |

Notes that matter for a reviewer:

- **`student_id` is an arbitrary caller-supplied string** (e.g. `"ada"`). Nothing
  authenticates it. It is chosen by whatever client calls `/v1`.
- **Timestamps are ISO-8601 UTC *text*** (`runtime/memory.py:69-70`), not native
  timestamps. They sort correctly but are stored as plain strings.
- **The data is not encrypted at rest.** It is a stock `postgres:16-alpine` data directory
  on the host volume. Attachment images/audio sit in the same volume as raw bytes.
- **The database has no per-student access control.** Any client that can reach `/v1` can
  list any student's threads (`GET /v1/conversations?student_id=…`, `routes.py:288`) and
  fetch any attachment by its integer id (`GET /v1/attachments/{id}`, `routes.py:377`).
  Attachment ids are sequential (`BIGSERIAL`), so they are trivially enumerable. The `/v1`
  surface itself carries **no authentication** — the security boundary is entirely "who can
  reach the nginx frontend on the LAN."

Everything in `muta-pgdata` survives `./run.sh down` / `docker compose down`. Only
`docker compose down -v` deletes it, and it deletes *all of it at once* (`RUN.md`,
"Persistence").

---

## 2. The three off-device data flows

By default Muta is **fully offline** — nothing student-related leaves the box. Three
optional flows can change that. All three are **off unless an operator sets the relevant
environment variables** (and, for web grounding, a per-request toggle). This section states
exactly what leaves the device in each, when, and how to keep it disabled.

### (a) Cloud boost — the largest exposure

*Code:* `orchestrator/gateway/deps.py:55-71`, `runtime/cloud.py`.

- **What leaves the device:** the **entire message list** the tutor assembles for the turn
  — the system prompt, the trimmed prior conversation history (up to
  `MUTA_RT_MAX_HISTORY_MESSAGES`, default **20** turns — `runtime/config.py:151`), and the
  current student message — is POSTed to a **third-party OpenAI-compatible API** at
  `MUTA_CLOUD_URL`, authenticated with `MUTA_CLOUD_API_KEY`. Because transcribed handwriting
  and transcribed audio become ordinary messages, image/voice content can reach the cloud
  in text form too.
- **When:** only when **all three** of `MUTA_CLOUD_URL`, `MUTA_CLOUD_MODEL`,
  `MUTA_CLOUD_API_KEY` are set (`deps.py:58`) **and** the connectivity probe (flow c) says
  the box is online (`cloud.py:44`, `deps.py:70`). It is process-wide: once configured,
  *every* student on the box is boosted whenever the box is online.
- **The disclosure gap:** the fallback is deliberately silent. `runtime/cloud.py`'s own
  docstring (lines 6-9) states that a cloud failure before the first streamed chunk is a
  "silent local retry — the student sees nothing but a normal answer." When the cloud *does*
  answer, the only signal is a **post-hoc** `source: "cloud"` field in the final SSE `done`
  event (`routes.py:276-279`), which the UI renders as a small badge **after** the answer.
  There is **no prior notice and no consent** — the student's full history has already left
  the device before any badge appears, and the student has no way to prevent it.
- **How to disable:** leave `MUTA_CLOUD_URL` / `MUTA_CLOUD_MODEL` / `MUTA_CLOUD_API_KEY`
  **unset** (the default — none are set in `docker-compose.yml`). Setting only two of the
  three is treated as a misconfiguration and ignored, not a partial enable (`deps.py:58`).

### (b) Web grounding — the student's question text

*Code:* `orchestrator/gateway/routes.py:188-206`, `orchestrator/gateway/websearch.py`.

- **What leaves the device:** the student's **raw message text** (`req.message`) is sent as
  the `q` query parameter to `GET {MUTA_SEARCH_URL}/search?q=…&format=json` (SearXNG shape —
  `websearch.py:29-35`). Only the current message is sent, not the history. The search host
  (and any network path to it) sees exactly what the child typed.
- **When:** only on `/v1/chat/stream`, and only when **all three** gates pass: the request
  carries `use_web: true` (a per-request field, off by default), `MUTA_SEARCH_URL` is set,
  and the connectivity probe says online (`routes.py:193`, `:196`). Any failure is
  fail-silent — the answer proceeds ungrounded.
- **The disclosure gap:** the retrieved `sources` are returned in the final `done` event
  (`routes.py:281`) and shown as a source list **after** the answer. As with cloud boost,
  this is post-hoc: the question has already been sent to `MUTA_SEARCH_URL` by the time the
  student sees where it went. There is no prior consent step.
- **How to disable:** leave `MUTA_SEARCH_URL` **unset** (the default), and/or leave the UI's
  web-grounding toggle off so requests never carry `use_web: true`.

### (c) Connectivity probe — metadata, every minute

*Code:* `orchestrator/gateway/connectivity.py`, started from `orchestrator/main.py:92`.

- **What leaves the device:** **no student data.** A background timer thread issues an
  `httpx.HEAD` request to `MUTA_NET_PROBE_URL` (default **`https://huggingface.co`**) with a
  3-second timeout (`connectivity.py:23`, `:37`). What it *does* reveal to that host — and to
  anyone observing the network — is the deployment's **public IP address, its existence, and
  the fact that it is powered on**, refreshed roughly **once per minute**
  (`MUTA_NET_PROBE_INTERVAL_S`, default 60). That is metadata about the school/site, not
  about an individual student, but for an air-gapped or privacy-sensitive deployment an
  unannounced heartbeat to a US-hosted service is still worth knowing about.
  (`run.sh:115` also probes the same URL once at host start-up.)
- **When:** continuously while the backend runs, independent of any student activity.
- **How to disable:** there is **no dedicated off switch**. Repoint `MUTA_NET_PROBE_URL` at
  a LAN or loopback host to keep the traffic on-premises, or lengthen
  `MUTA_NET_PROBE_INTERVAL_S`. Note a useful side effect: cloud boost (a) and web grounding
  (b) both require the probe to report `online() is True`, so if you point the probe at a
  target that never succeeds, `online()` stays `False` and **flows (a) and (b) can never
  activate** — a locked-down probe target is also a hard gate on the other two.

### Summary

| Flow | What leaves | Trigger (all off by default) | Disable |
|---|---|---|---|
| (a) Cloud boost | full system prompt + up to 20 turns of history + current message → third-party API | `MUTA_CLOUD_URL` + `MUTA_CLOUD_MODEL` + `MUTA_CLOUD_API_KEY` all set, and online | unset any of the three |
| (b) Web grounding | current student message text → `MUTA_SEARCH_URL` | `use_web:true` + `MUTA_SEARCH_URL` set + online | unset `MUTA_SEARCH_URL` / UI toggle off |
| (c) Connectivity probe | HTTP HEAD (no student data; reveals IP + liveness) | always on while backend runs | repoint `MUTA_NET_PROBE_URL` to a LAN/loopback host |

---

## 3. Regulatory context (what an operator must consider)

This is orientation, not legal advice. Confirm the applicable obligations with counsel for
your jurisdiction.

**Nigeria — NDPA 2023 (Nigeria Data Protection Act).** The operator deploying Muta is very
likely the **data controller** for the students' personal data. Points that bite here:

- **Children's data / consent.** Processing a minor's data generally requires the consent of
  a parent or guardian. Muta captures no consent today (see §4).
- **Lawful basis and data minimisation.** You must be able to state the lawful basis and
  collect no more than needed. Muta stores full message transcripts and raw images/audio
  indefinitely.
- **Security safeguards.** The Act expects appropriate technical measures. Data at rest is
  unencrypted and the `/v1` surface is unauthenticated (§1).
- **Cross-border transfer.** Cloud boost (flow a) can send children's data to a third-party
  API that may be **outside Nigeria**. Cross-border transfer of personal data carries
  specific NDPA conditions; naming the recipient and its location in your records is the
  minimum.

**GDPR-class expectations (as a good-practice baseline, and if any EU nexus exists).**

- Art. 8 — conditions for a child's consent to information-society services.
- Art. 5 — data minimisation and **storage limitation** (there is no retention limit today).
- Arts. 15-17 — rights of **access, portability, and erasure** (no export/erase endpoint
  today — §4).
- Art. 32 — security of processing, including **encryption at rest** where appropriate.
- Arts. 44-49 — restrictions on **international transfers** (cloud boost).
- Art. 35 — a **DPIA** is expected for large-scale processing of children's data.

**FERPA-class expectations (US-school framing, useful as a checklist even where FERPA does
not formally apply).** Student work and tutoring records are education records; disclosure
to a third party (e.g. the cloud provider behind flow a) generally needs consent or a
defined exception, and the school remains custodian of the records. Treat any cloud/web
enablement as a third-party disclosure decision, documented and consented.

---

## 4. Current gaps (known issues)

These are real and tracked in the project's **production-readiness audit**. None of them is
fixed in the code today.

1. **No consent flow.** Nothing asks the student or a guardian for permission before storing
   their work, and cloud boost / web grounding surface only a *post-hoc* badge — never prior,
   informed consent. There is no guardian-consent capture anywhere.
2. **No retention policy.** Conversations, messages, and attachments persist in `muta-pgdata`
   forever. There is no per-student expiry, no time-based purge, no automatic deletion. The
   only bulk delete is `docker compose down -v`, which erases everyone at once.
3. **No student-data export or erasure endpoint.** `DELETE /v1/conversations/{id}`
   (`routes.py:361`) removes a single thread (cascading its messages and attachments), but
   there is **no** "export everything for student X" and **no** "erase student X" operation.
   A subject-access or erasure request cannot be fulfilled without hand-written SQL against
   the database.
4. **No encryption at rest.** The Postgres volume — including raw image and audio bytes — is
   plaintext on the host disk.
5. **Orphaned attachments persist.** An attachment is written before it is linked to a
   persisted message (`routes.py:570-576`), and can be stored with a `NULL`
   `conversation_id`/`message_id` (`runtime/memory.py:216-231`). Cascade deletion only fires
   through a set `conversation_id`; on message delete the link is `SET NULL`
   (`runtime/memory.py:47-55`). An upload that is never linked — or whose conversation is
   never created — is never garbage-collected and lingers indefinitely, unreachable through
   the UI but present in the volume. There is no GC job.
6. **No authentication / access control on `/v1`.** Any device that can reach the frontend
   can enumerate attachments by sequential id and list any `student_id`'s history (§1). The
   only boundary is network reachability.
7. **No off-device audit trail.** There is no log recording *when* a student's data was sent
   to the cloud or a search host, so a later "what left the box, and when?" question cannot
   be answered from records.

---

## 5. Recommended posture before a school deployment

A pragmatic checklist. Items map to the flows and gaps above.

- [ ] **Stay offline by default.** Leave `MUTA_CLOUD_*` and `MUTA_SEARCH_URL` unset. Point
      `MUTA_NET_PROBE_URL` at a LAN/loopback host so nothing phones out (this also hard-gates
      flows a and b).
- [ ] **Isolate the network.** Keep the stack on a classroom LAN/VLAN. Do not expose ports
      `3000`/`8000` beyond it. The DB port (`15432`) is already bound to `127.0.0.1` — keep
      it host-only.
- [ ] **Get consent first.** Obtain guardian/school consent covering on-device storage of
      children's work *before* first use. If you ever enable cloud boost or web grounding,
      obtain **explicit, informed** consent for third-party processing and name the provider
      (the `MUTA_CLOUD_URL` / `MUTA_SEARCH_URL` operator) in your data map.
- [ ] **Encrypt the disk.** Enable full-disk / volume encryption (LUKS, FileVault, or the
      cloud provider's encrypted volumes) since Postgres stores everything in plaintext.
- [ ] **Define a retention window and enforce it manually.** There is no auto-expiry;
      schedule periodic purges (or a `docker compose down -v` at end of term) and document
      the schedule.
- [ ] **Have a manual access/erasure procedure.** Until export/erase endpoints exist, keep a
      documented SQL runbook keyed on `student_id` for access and erasure requests.
- [ ] **Protect the cloud key.** If cloud boost is enabled, keep `MUTA_CLOUD_API_KEY` out of
      committed files and out of the compose `environment:` block (it is visible via
      `docker inspect`). Use an `env_file` or compose secrets — see
      [`configuration.md`](configuration.md#secrets-handling).
