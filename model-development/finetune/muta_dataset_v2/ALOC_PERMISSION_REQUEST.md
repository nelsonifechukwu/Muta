# Draft: ALOC bulk-export and AI-training licence request

This is a project-side requirements draft, not legal advice. Send it through the
[ALOC contact channel](https://www.aloc.com.ng/contact) or to the legal/contact address published
by ALOC. Replace bracketed fields before sending. Do not include API keys in the message.

## Suggested subject

Request for written ALOC bulk-data and AI-training licence for the Muta offline STEM tutor

## Suggested message

Dear ALOC Station team,

We are developing **Muta**, an offline adaptive tutor for secondary-school mathematics and
scientific reasoning, for [competition/research organization and submission]. The deployed tutor
must operate without a network connection. We would like to license a defined export of ALOC's
historical examination content for dataset construction and model development.

We have reviewed ALOC's Developer Terms v2.3.0. We understand that standard plans limit caching,
prohibit permanent wholesale synchronization and systematic cursor traversal, and prohibit using
ALOC API content to train, fine-tune, evaluate, or benchmark an AI model. We therefore will not use
ordinary API access for this purpose without a separate signed agreement.

Please quote for a bespoke licence and preferably a server-side bulk export covering:

- exam types: WAEC/WASSCE, JAMB/UTME, NECO, state-board examinations, and Post-UTME;
- countries, institutions, years, sittings, and source-paper identifiers included in the export;
- STEM subjects: mathematics, further mathematics, physics, chemistry, biology, agricultural or
  integrated science, and any other mutually agreed scientific-reasoning subjects;
- fields: stable question ID, question text or HTML, answer options, verified answer key, subject,
  exam type, year, country, institution/state, paper/section/passage grouping, and correction or
  withdrawal history;
- optionally and priced separately: ALOC topic/difficulty metadata and human/AI explanations.

The signed agreement must expressly authorize the following uses for the named Muta project:

1. a complete documented bulk export, or an automated server-side retrieval method approved by
   ALOC, without violating the standard cursor-traversal or anti-scraping clauses;
2. permanent encrypted/offline storage and reproducible snapshots after a subscription ends;
3. normalization, deduplication, error correction, answer verification, format conversion, and
   creation of derived tutoring examples;
4. internal human review and use in model evaluation and benchmarking;
5. training and fine-tuning neural-network/LLM adapters and merged models;
6. submission of the resulting adapter/model weights and provenance evidence to competition
   judges, including offline deployment on the competition device;
7. [if desired] later public or commercial distribution of adapter or merged-model weights,
   without distributing the raw ALOC question bank;
8. the agreed territory, duration, renewal/termination terms, retention/deletion obligations, and
   attribution wording.

Please state explicitly that this bespoke agreement overrides the conflicting restrictions in
sections 4, 6, and 8 of the standard Developer Terms for the licensed scope. A standard API plan,
credit top-up, or generic enterprise bulk-data entitlement alone will not be treated by us as an
AI-training licence.

Because the requested material includes historical exam content, please also confirm in writing:

- which content ALOC owns, which content it licenses, and which content it supplies under another
  asserted legal basis;
- ALOC's authority to grant the requested training, derivative-use, permanent-storage, and
  model-weight rights for each exam body;
- whether separate permission from WAEC, JAMB, NECO, a state board, or a university is required;
- any source-specific attribution, non-redistribution, geographic, or duration restrictions;
- how corrections, disputed answers, withdrawals, and takedown requests will be communicated.

For our provenance record, please include an executed agreement identifier and effective date, an
inventory of covered exam bodies/years/subjects/fields, the delivery method, the permitted row or
question count, and a contact for rights or takedown notices.

Until such an agreement is executed, we will make no authenticated extraction request for this
purpose and will include no ALOC content in Muta's training or evaluation datasets.

Kind regards,

[Name]\
[Organization/project]\
[Email]\
[Competition/research context]

## Evidence to archive if permission is granted

- executed agreement and all amendments;
- ALOC's written scope/authority response and any separate exam-body grants;
- invoice/order form identifying the bespoke licence, not merely API credits;
- delivered source inventory and transfer receipt;
- exact export files, byte sizes, SHA-256 hashes, retrieval date, and delivery method;
- attribution text, territory, duration, termination, deletion, and takedown requirements;
- the adapter/build code version and manifest for the first quarantined ingest.

The first licensed ingest should remain quarantined and evaluation-only until its exact scope,
lineage, answer quality, duplicates, and contamination risk have been audited. Training should be
enabled only after the executed agreement expressly covers it and the registry entry is changed in
a reviewed commit.
