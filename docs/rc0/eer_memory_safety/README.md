# RC0 D10: host EER memory safety (#221)

Base: `71ab841e69869b615555bb02f8f393db59c22d73`. Work is pending native
qualification and independent review; no merge recommendation yet.

## Design and preserved behavior

The host's paired 7-bit unpackers keep their bit operations and electron order.
Each loop starts only inside the fraction, counts consumed bits (including the
final run length), and rejects consumption past that fraction. `memcpy` replaces
unaligned 32-bit dereferences without changing the word's bits. Eight zero bytes
at the allocation end make speculative reads safe; bytes read ahead from the next
fraction cannot make an overrun acceptable. The 8-bit unpacker checks availability
of each consumed run/symbol. A pair-capacity check bounds electron-vector writes.
No partial fraction is rendered: an overrun/overshoot takes the inherited D6 warning
and skip path. Valid streams retain the same positions, symbols and accumulation.

Container errors are different: invalid strip sizes/ranges, failed directory
selection/read and missing mandatory tags fail the movie. Lazy reading records an
`exception_ptr` inside the critical section and rethrows outside it, where the
runner's existing per-frame capture and serial per-movie handler apply. TIFF/FILE
handles close with scope guards. Read-only input fixtures are never modified.

Legacy footer indexing validates remaining bytes and word counts before subtracting
or multiplying. Geometry-less legacy files are refused explicitly. Whole-IFD
truncation remains the inherited E-1 shorter-movie behavior without expected counts.
MRC byte-order magnitude tests use ordered comparisons, integer formatting uses an
unsigned magnitude for INT_MIN, and temporary MRC headers are freed on parse errors.

`EerMemorySafety` generates small TIFF/EER and MRC fixtures at test time. Its scalar
encoder and expected sparse image check valid pixels exactly, including grouping,
upsampling and terminal electrons. Corrupt fractions must equal an omitted fraction;
container/header failures must exit 1, complete movie 2, publish no failed-movie
products and withhold the joint completion STAR. The test is required by the existing
fail-closed collection validator.

## Provenance

Started from the Opus partial patch (SHA256
`f544d17693f24e610a9b3797107c65c22241a290cfac0e571717a112cee44be7`), reused
initialization, handle guards, legacy/footer checks, header/formatting fixes,
paired-loop bounds and helper modes. Corrected the 8+4 partial-symbol acceptance,
added physical strip-range validation and catch-all exception transport, and wrote
the generated regression and qualification evidence here. The original worktree
was read only and remains untouched.
