# PR125 reviewed with the same matrix

The memory owner's no-gain RSS fix (`t3code/fix-compact-ingest-memory-regression`,
head `fb0f653`) run through the unmodified support matrix, rather than a second
production implementation.

Their branch was cloned and built without modification; the harness was invoked
from this branch with `--binary` pointing at their build, so nothing in their
tree was touched. Both runs used the same host, the same device and the same
deterministic fixtures.

`support-matrix.json` is their run: 16/16 rows, 28/28 arms UUID-witnessed.
`product-equality.json` joins it against `../vm-4gpu/support-matrix.json` —
identical inputs, and **38/38 products byte-identical** in header, extended
header and payload across the two production sources.

This is product and support equivalence at the matrix's synthetic geometries. It
is not a memory result: no RSS was measured here, and the +0.230 GiB no-gain
regression their PR exists to fix is theirs to demonstrate. It is also not a
real-data result.
