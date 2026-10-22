# M2 evidence retention — unapproved decision brief

Current source-only inventory is pinned to C1 `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`
against main `3691374061f782bc84531fd1c79d017ddcb5a7c2`.
`M2_c1_docs_inventory_e77a51a2.json` and `inventory_c1_docs.py` retain the method
and exact Git tree identities. This is a byte/path inventory, not source review,
native qualification, pack-size measurement, or adoption of a retention policy.

The changed current documentation blobs total 48,385,636 logical bytes across
756 files (48,300,778 unique blob bytes). Eleven archives account for 38,643,183
bytes. The largest, inherited through the selected #269 stack, is
`docs/post_rc0/s1/km_truth/raw.tar.gz` (34,973,613 bytes). These are complete
changed-blob sizes, not predicted compressed Git transfer or incremental disk cost.

The separate #273 integration packet's 36 unique documentation paths and #274's
32 are absent from this C1 tree. Their exact source heads and historical evidence
remain on their existing published branches. The #275/#276 diagnostic packets
are likewise not selected C1 layers. Excluding those layers does not mean the
remaining component branches contain no bulk evidence; the inventory shows it.

M2 choices for the maintainer:

1. Retain this selected-component evidence tree and keep #273/#274 integration
   packets archived on their branches. This needs no candidate source rewrite,
   but keeps the existing component archive footprint.
2. Extract a compact main-tree acceptance/index record and retain the bulky
   component/integration evidence at pinned immutable commit/archive references.
   Before any extraction, freeze the complete inventory, archive digests,
   retrieval links and retention owner, verify retrieval and licence/access,
   and independently check that no source/test fixture or required acceptance
   evidence was accidentally removed. A docs-only candidate revision still
   needs explicit source-tree/provenance accounting; do not credit its new SHA
   with tests from an earlier SHA without that distinction.
3. Keep all evidence including #273/#274 on main only by explicit scope change;
   this is outside the presently selected C1 layers and must not silently merge
   diagnostic production overlays or old integration histories.

No file, archive, branch or input has been removed. No remote cache or historical
PASS/FAIL/UNRUN record has changed. A retention decision is not permission to
relax validation or merge C1, and archive existence is not provenance by itself.
