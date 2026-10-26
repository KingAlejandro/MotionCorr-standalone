# Bounded numerical reproduction; material interpretation correction

The eight fixed-point pairwise gaps reproduce within `1e-14` using independent parent Fourier-series evaluation. The original numerical RESULT is supported within this scope. Its section 3 causal discussion is **not cleared**.

On bad patch `(62,79)`, frame4 iteration1, the four reference terms contribute objective gaps `+0.0382561273`, `+0.0153357080`, `+0.0001590117`, `-0.0148742570` between the fixed aggregate native-selected point and the explicit observed-frame0-gauge physical scoring point. They sum to `+0.0388765900`; the primary native-map gap is `+0.0388765339`, with a `-5.60e-8` numerical remainder. The frame0 term is the largest positive contribution, while frame3 opposes the remote point. Contributions from frames1–3 nearly cancel. This is an algebraic observation about two fixed points, not causal shares, a noise-origin proof, or a demonstration that the whole physical neighbourhood is inferior.

Central patch `(62,47)` gives four positive gaps `0.0024249769`, `0.0038494956`, `0.0131281039`, `0.0006569033`. Pairwise map regeneration differs from the primary native maps by at most `1.50e-7` and `1.91e-7` respectively. No native FFT was rerun. The parent's check does not independently audit the original worker's component peak/local searches or leave-one-reference-out candidates.

## Material correction to original REPORT section 3

The original discussion quotes `G4=(-3.185,+1.498)` and `G1=(-0.905,+0.898)`. Those are not the captured trajectory. Directly retained `global-shifts.bin` gives `G0=(0,0)`, `G1=(-0.604719206927727,0.5450050278665695)` and `G4=(-2.2801393506129037,0.5656077519907101)`. The numerical script itself loads the correct captured G, so this reporting error does not alter the supported table.

The original sentence beginning “Because global alignment ...” additionally infers larger uncompensated boundary wrap/window mismatch as a cause. These fixed-state arrays do not establish that explanation. Treat global error, additive noise, clipping/shear, spectral weighting and reference composition as unresolved possible interactions. Retain original REPORT/RESULT/scripts/manifest unchanged; this additive review supersedes only that unsupported discussion.

## Next discriminator, not yet executed

A noiseless comparison could be useful only after verifying identical underlying truth/scene and applying **the exact captured G**, preprocessing and crop geometry. Comparing two independently aligned noisy/noiseless trajectories would not isolate noise. First reproduce the captured noisy patch samples and spectral state with a source-pinned saved-data bridge; only then change noise while holding G and the physical scoring convention fixed. Any regenerated map stays auxiliary until its discrepancy from the primary native map is measured. This proposal does not authorize temporal reference pruning, a confidence threshold, estimator adoption or new native producers.

Performed locally with existing Python/NumPy2.4.2 and BLAS/OpenMP caps1. All original four manifest hashes verify. No source/repository change, SSH/native execution, estimator fit, movie pixels or global certification was part of this reproduction. Exact model provenance is retained separately from the original worker's abbreviated model label.
