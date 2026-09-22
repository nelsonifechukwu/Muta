# Final known-suite P2 continuation

## Diagnosis

The sealed two-candidate addendum stopped at its duplicate-integrity gate because
the untouched DeepSeek control spent all 1,024 generated tokens in reasoning and
returned an empty answer for both duplicate prompts. This is an observed
answer-delivery failure, not missing data. P2 completed both prerequisite gates
normally and with duplicate-identical output. Judges and STEM inference never
started for either candidate.

## Bounded continuation

Do not retry DeepSeek and do not overwrite the failed attempt. Run only the
previously unexecuted judges and STEM suites for P2, with the same immutable
model, server, prompts, generation settings, and shared GPU lock. The controller
must first bind the original manifest and failure receipts by SHA256, verify the
P2 smoke completion marker and response bytes, and verify the new one-candidate manifest is an exact subset
of the original manifest. It writes to fresh output and control directories.

DeepSeek remains a failed control in the final table. This continuation fills
only the missing P2 known-suite cells needed to compare P2 with the sealed
historical incumbent.
