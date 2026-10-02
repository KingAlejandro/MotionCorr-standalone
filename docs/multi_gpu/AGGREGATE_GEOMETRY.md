# Aggregate-only declared geometry boundary

Issue142 reproduced ordinary resume publishing bin2 (2 Å) joint metadata over
retained bin1 (512x512, 1 Å) products. The initial aggregate-only candidate had
the same defect. Its retained actual-binary reproduction is not a claim that
processing identity is already solved.

The new aggregate-only preflight additionally requires declared binning to
agree with saved per-movie binning, effective declared original optics sampling to
agree with saved sampling, and main/noDW/EVN/ODD MRC dimensions and X/Y sampling
to agree with the declared output. Requested power-spectrum dimensions are
checked separately because PS sampling follows a different reconstruction
contract. Every original movie is checked before aggregate staging/publication;
a refusal names its movie and leaves per-movie content and mtimes unchanged.
A relative 1e-6 representation allowance accounts for decimal STAR serialization
and MRC float32 sampling, not scientific pixel comparisons.

Actual-binary controls reject changed binning, changed original optics sampling,
wrong retained MRC sampling and wrong retained MRC dimensions. All four failed
the pre-repair candidate. A genuine matching bin2 result passes, so this is not
a blanket rejection of binning. Same-invocation controls also accept optics
that override a contradictory raw CLI pixel size, and distinct per-movie optics
groups. Initialisation fills missing declared optics from CLI; supplied optics
are the authority used during processing and aggregation. The gate changes no pixels or ordinary resume.

**Remaining Issue142 limitation:** these checks do not bind input content,
gain/defect identity, dose, selection/grouping, algorithm/backend identity or
all processing options. Changed inputs/options with the same output geometry
still require a versioned completion-identity contract and legacy-output policy.
This endpoint is intended to assemble the same frozen worker invocation; merger
hash/mtime checks additionally protect staged products from rewriting. Do not
advertise arbitrary compatible-resume validation or scientific configuration
identity. Native product arms and real report-content acceptance remain UNRUN.
