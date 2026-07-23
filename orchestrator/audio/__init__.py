"""Audio lane — ASR in, TTS out, and the math-to-speech normaliser between (TDD §6.6, §7.7).

The engines are sherpa-onnx binaries that ship in the bundle; everything here is the thin
Python that drives them, plus the one piece that is pure logic and therefore testable
offline: turning `\\frac{3x}{2}` into "three x over two". A TTS voice handed raw LaTeX reads
it as punctuation, which is the difference between a tutor and a modem.
"""
