# Input backends for real acquisition formats

Question: can original real-world acquisition formats reach the resident GPU
engine efficiently, without changing MotionCorr's result and without
materialising a host float movie?

Answer, for TIFF: yes for every unsigned 8- or 16-bit TIFF LibTIFF can decode,
by routing it through the compact native-sample staging that already existed
for 16-bit input. The host float movie disappears; the codec work does not.
For Deflate specifically the codec work also moves to the GPU, now including
8-bit samples and multi-row strips. EER and compressed MRC are untouched and
unmeasured here.

| document | contents |
|---|---|
| `RESULTS.md` | format census, route matrix, correctness gates, measured performance and memory |
| `FAILURE_POLICY.md` | per-route failure categories and the nvCOMP trust boundary (#134) |
| `harness/` | decoded-sample oracle and campaign tooling |
| `six_movie_manifest.json`, `two_movie_manifest.json` | product manifests for `compare_output_trees.py` |

## Reproducing the inputs

Every input variant is generated losslessly from the RELION tutorial movies by
`harness/gen_matrix.py`: one decode per source movie, every variant written
from the same in-memory sample array. The tutorial movies are counting-mode
data whose maximum sample is 68, so a uint8 re-encode is value-lossless and is
refused outright if any sample would not fit. That is what makes "the same
movie in another format must produce the same products" a usable gate rather
than an approximation.
