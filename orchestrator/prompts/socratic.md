<!--
Socratic mode system prompt.

STABLE PREFIX FIRST: keep every invariant instruction above the per-student block so the
llama.cpp prompt cache (ROADMAP 17 Jul) hits on the shared prefix. All variable, per-student
text goes last. Prompt architecture is a performance decision here, not only a pedagogy one.
-->

Answer as the user requires

--- per-student context (variable — keep last) ---
