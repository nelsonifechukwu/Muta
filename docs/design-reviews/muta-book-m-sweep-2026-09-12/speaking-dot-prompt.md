# Speaking-dot experiment

Mode: built-in image generation, precise edit of the user-supplied clean-book board.
Output: `d-speaking-dot.png` — visual concept for review.
Change: each existing square becomes a compact square speech mark with a small tail. The
wordmark mark remains below u, and the same visual motif is reused below the standalone book
at the user's suggestion. Pages remain unobstructed.

## Exact prompt

The final result is a generated concept, not an exact vector or pixel-preserving edit. The first
output had prominent tails; the second pass shortened and tucked them. Page proportions also
drifted slightly from the source, which should be resolved in an eventual vector drawing pass.

## Tail refinement prompt

Use case: precise-object-edit. This Muta logo board is nearly finished. ONLY refine the three tiny square speech marks (under u, under the app-icon book, under the black book). Make every triangular speech tail HALF ITS CURRENT LENGTH and tuck each tail fully inside its square body's left/right bounds. For the large left wordmark square approximately 43 pixels wide: the tail must extend only about 7 pixels below the bottom edge, with its leftmost point aligned to the square's left edge, never protruding to the left. Use the same tail-to-body proportion in the smaller two marks, about 5 pixels down. Keep ALL THREE square BODIES pixel-identical in size, placement, color and corner rounding. Do not change the book, wordmark, background, app-icon tile, typography, labels, overall composition or any other feature. This is a minuscule typographic correction, not a redesign. The final shape should look like a square punctuation mark with a discreet short speech nib; retain a generous rectangular square body.

## Initial edit prompt

Use case: precise-object-edit / logo-brand. Edit the supplied Muta open-book identity board with one very small, precise design change. The user wants the EXISTING SQUARE DOT ITSELF to suggest dialogue, combining its importance in the name with a conversation cue. Do not place any speech bubble on the book pages. There are exactly three squares to modify: (1) the terracotta square directly beneath the u in the large Muta. wordmark at left, (2) the terracotta square directly beneath the book in the upper-right forest app icon, (3) the black square beneath the lower-right monochrome book. In ALL THREE, preserve the existing square body, approximate size, color and position, and add ONE tiny attached triangular speech tail near its lower-left corner. The tail should project diagonally down-left from the lower edge but remain within the square body's horizontal footprint, only about 20 percent of the square body's width; keep corners subtly rounded as they already are. It must remain square-like and compact, more typographic punctuation than an ordinary large chat bubble. No interior dots, line, letter or symbol. Keep the square BODY optically centered under the u; do not center the total square+tail silhouette under the word. The corresponding speech-dot beneath each standalone book is centered under its spine. Do not enlarge or lift the marks toward the book. No detached triangles. Keep all other graphic content unchanged: natural open-book curves and binding, ivory/terracotta pages, forest rounded-square tile, exact elegant serif wordmark 'Muta.', all positions, white background and generous spaces. Keep the interior of all pages completely clear. Change only the bottom caption from 'B / OPEN BOOK' to 'D / THE SPEAKING DOT' in matching understated typography. Render a precise, polished logo study; retain the same 1536x1024 landscape layout. No additional shapes, no invented M stems, no cubes, no shadows or textures added.
