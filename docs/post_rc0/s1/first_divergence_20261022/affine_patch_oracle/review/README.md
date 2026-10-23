# Review provenance

Round 1 is a fresh independent Opus review of commit `07773483`
(`round1/REPORT.md`, SHA-256 `b5a5f4f762fe934d6d842fc212d6c67438ac0162e8362eb0e64cdf72949d8c05`).
The reviewer's report, scripts and outputs are copied byte-for-byte from the
reviewer directory; nothing in `round1/` was edited.

Provenance notes:

- `round1/SHA256SUMS.txt` is the reviewer's file, retained verbatim. Its own line
  (`./SHA256SUMS.txt`) is invalid by construction because a file cannot contain its
  own hash; `shasum -c` fails on that line only. The other 17 lines verify against the
  copies. `round1-artifacts.json` binds the copied files independently, with the
  hash of `SHA256SUMS.txt` as actually retained.
- The reviewer directory also contained a subdirectory `opus-r1-independent/`
  written by a different task after the review started, and a `scratch/` temporary
  directory. Neither was read, copied or hashed here. The reviewer's process note
  records the unowned writer; the parent is investigating it.
- Reviewer scripts carry no individual SPDX line and are not edited, because their
  bytes are hash-bound.
- Author responses are in `round1-response.md`. The mechanical corrections were made
  by the author as a summary-only commit; they are not a new independent review.
