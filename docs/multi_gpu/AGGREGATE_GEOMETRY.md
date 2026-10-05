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

## Tomographic final-reference publication

Aggregate-only tomography writes per-series tables into private staging while
storing their final output paths in the joint `rlnTomoTiltSeriesStarFile` fields.
The staged writer checks open/write/flush/close and rejects escaped, duplicate,
or joint-marker-colliding per-series targets. Nested per-series files publish
first; the joint table's final references must be readable as a complete
TomogramSet before report files and finally the joint success marker publish.
Repeating aggregation supports existing nested output directories. Ordinary
TomogramSet writing and ordinary resume are unchanged.

Actual CPU binary controls use two tomograms with nested per-series tables and
ordered tilt/movie/model/exposure associations. The predecessor exited0 but
left references to deleted `.aggregate-*` paths; the new oracle rejects that
false success. Candidate controls require readable final references, unchanged
movie payload/header/STAR/EPS bytes and mtimes, repeated aggregation, and normal
refusal/no joint success for partial movies, blocked final sidecar destinations
and a per-series reference colliding with the joint filename. Explicit fake
Ghostscript controls cover reference/publication logic only; real rendering and
CUDA execution remain separate native gates. Publication is joint-last, not a
rollback transaction for already published auxiliary/per-series files, and no
crash-durability or full processing-identity guarantee is added.

Final per-series STAR destinations are also admitted before private staging:
they cannot alias a known per-movie MRC/model/log/plot destination or an aggregate
report. The actual `Movies/a.star` collision control fails the previous repaired
binary (exit0 and replaced movie metadata), then requires named refusal, no new
joint/report, and identical movie bytes/mtimes from the corrected binary.
A `logfile.pdf` reference additionally proves report-target admission. Existing
canonical joint/report files from an earlier invocation are retained on failure;
no rollback or stale-marker invalidation guarantee is added.
