# Lane B output parity: the flag changes no product

Source `7f8788c` (one commit on `origin/main` `8323c55`). macOS 26.7,
AppleClang, `-DCMAKE_BUILD_TYPE=Release`. Input
`20170629_00021_frameImage.tiff`, sha256
`df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0`.

Corrected images are compared from byte offset 1024, because the MRC header
carries a build timestamp and a whole-file hash is not reproducible.

Common arguments: `--use_own --j 4 --dose_weighting --dose_per_frame 1.277
--patch_x 5 --patch_y 5 --bfactor 150`.

## Whole movie

| arm | pool engaged (per-movie log) | corrected image | per-movie STAR |
|---|---|---|---|
| `--persistent_tiff_readers` absent | no, one open per frame | reference `b745593f…` | reference |
| `--persistent_tiff_readers 4` | `Persistent TIFF readers: 4` | identical | identical |
| `--persistent_tiff_readers 12` | `Persistent TIFF readers: 12` | identical | identical |

Negative control: the same run with `--last_frame_sum 20` produces a
**different** hash, so the comparison can distinguish two real results.

The engagement column is not decoration. An earlier attempt at this table
passed with all three arms identical because the shell had folded
`--persistent_tiff_readers 4` into one argv entry, the parser rejected it with
a warning, and every arm silently ran the reference path. The per-movie log
line is what separates "the experiment preserved the output" from "the
experiment never ran".

## Selected frames

`--first_frame_sum 3 --last_frame_sum 19` (frames 3..19), pool size 5:
identical corrected image, and different from the 24-frame run, so the
selection is real.

## Batch isolation with a damaged movie

Two movies, the first a 50% prefix of the second.

| arm | exit | message | healthy outputs retained | joint STAR |
|---|---|---|---|---|
| off | 1 | `Movies/damaged_movie.tiff: Corrupted TIFF directory structure: TIFFAdvanceDirectory: … Error fetching directory count` | yes | withheld |
| `--persistent_tiff_readers 4` | 1 | identical text | yes | withheld |

The healthy movie's corrected image is byte-identical between the two arms.
