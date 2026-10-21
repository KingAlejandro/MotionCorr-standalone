# S1 peak-fit attribution (#257, #238)

Work in progress. This branch contains evidence and diagnostic patches only. The independent production fix is PR #260. Nothing here changes production defaults, gates, tolerances or the RC0 qualification state.

The full census is 10216, 12963 and EMPIAR-10474 Falcon 3, ten movies per family, both 5×5 and 3×3 grids (60 configurations). Primary CPU references, recipes, S1 threshold (relative RMSE ≥0.1) and two-sided exact McNemar convention are those of PR #255 at `23a320a65aafaa41631a051f49e2c36ad99092dd`.

A0 is PR #254 at `8b55d5dae8815e4648758620750496e4acd533c5`, with #250's observation-only captures reapplied. A1 adds precisely #257's double promotion. A2 uses A1 and zeros only the CCF spectrum's DC bin immediately before each actual CCF C2R. This is a diagnostic change: in exact arithmetic it subtracts a map constant and preserves peak positions and curvature. On float maps it can change samples, winners, fitted candidates and subsequent feedback.

The two nulls retain A0 arithmetic and add random-sign, axis-wise magnitudes of the promoted-minus-native-float candidate evaluated on the same five samples, after applying the unchanged float scale. The perturbation is added directly to the actual native baseline candidate; the host float replay is used only for emulation diagnostics. The sign is hashed from seed, patch, iteration and frame; seeds 1 and 2 are used. This is a conditional mechanism-dose null, analogous to #255's per-frame row-term null: its target is the same-map arithmetic correction, not the accumulated trajectory difference after feedback. Per-axis magnitudes, and therefore vector norm, are preserved before the final float output rounding. The retained null records allow that match to be checked rather than assumed.

All 42 retained 4GPUs CPU products are reused. The nine SCARF movies' 18 CPU MRC products were deleted by #255's published runner; searches of its retained directories found metadata/logs only. Only those references are regenerated with the retained frozen-F CPU binary, same input hashes/STARs and recipe on gn0003. The #254 parent and A0 must reproduce #255's reported values before those configs enter pooled analysis.

Global-only products are a separate recipe, with patch arguments removed and `--save_noDW`, reusing the existing two #255 CPU global-only products and generating missing ones. Extra CPU runs used to capture first divergences are checked byte-for-byte against the primary sweep references; they do not replace those references.

Release builds only. Each 4GPUs run is eight-CPU affinity capped and holds its selected GPU's advisory lock, with GPU selection by UUID and a descendant-process UUID witness. Independent correctness work shares the host; timings from these diagnostic runs are not performance measurements. SCARF uses an eight-CPU gpu-devel allocation, CUDA 12.8 and `/tmp` scratch; no batch output goes to `/work4`.

The C++ scalar metric helper implements the same population-standard-deviation denominator as `compare_motioncorr.py`. It avoids a NumPy dependency for independent analysis on 4GPUs. SCARF uses the original comparator. S1 screen status is separate from the backend gate verdict.

The initial null implementation used a host float replay as its baseline. It is retained as a preliminary arm. Final nulls add the matched dose to the actual native candidate (`7fe2864e`), removing any dependency on exact host emulation.

Preserved administrative attempts: two global drivers waited for GPU3's correctness lock without executing a movie, then were moved to the occupied census lanes using the same lock protocol. One CPU capture was terminated after discovery that the host has CPUs 0–123 and a requested 120–127 mask would grant only four CPUs; its partial output/exit is retained under `attempts`, excluded from evidence, and rerun with eight valid CPUs. No lock file or unrelated process was removed.

The fit evaluates the stored samples accurately; it cannot recover contrast lost when the CCF was formed. The 0.13525164 px earlier replay maximum was already in scaled image/patch pixels. Earlier first-iteration observations are not bounds on accumulated final trajectory error. CPU agreement remains Tier B evidence; known-truth and S1.4 scientific outcomes, and production performance cost, are unrun here.
