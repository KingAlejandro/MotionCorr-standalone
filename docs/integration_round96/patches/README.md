# Reusable patch mapping for #72 / PR102

The Codex review finding on PR110 ([`r4119221898`](https://github.com/KingAlejandro/MotionCorr-standalone/pull/110#discussion_r4119221898), P2, at `f9650704`) lands in three files that **#72 / PR102 owns**:

- `test-data/generate_known_motion_fixture.py`
- `tools/verify_fixtures.py`
- `test-data/known_motion/MANIFEST.json`
- (plus the control in `tools/test_ci_fail_closed.py`)

It is fixed **once**, here, by the correctness-integration owner, because PR110 is the tree where the defect is reachable end to end and where the combined suite can demonstrate the before/after. **PR102 should not reimplement or overwrite it.**

## The two commits

| patch | commit | what it changes |
|---|---|---|
| `0001-…` | `b0a70d6` | production fix: canonical mode stops rewriting the committed `.star` and compares instead; `star_sha256` added to the manifest schema, the manifest, and the per-case verification |
| `0002-…` | `13c6e32` | Control 8: discriminating maintained-entrypoint negative control, plus staging the `.star` into Controls 5 and 6 |

## How PR102 should take it

Three options, in order of preference.

**1. Do nothing (recommended).** Land PR102 first as the merge order already recommends, then land PR110 on top. The fix arrives with PR110 and PR102 needs no change. This is the path the published merge order assumes.

**2. Cherry-pick, if PR102 must carry it standalone.** From a checkout with this branch fetched:

```
git cherry-pick -x b0a70d6 13c6e32
```

Both commits touch only #72-owned files plus `tools/test_ci_fail_closed.py`, so they apply to PR102's head with no dependency on #92, #98 or #99. Verified: neither commit touches `src/**`.

**3. Apply the patch files**, if the branch is not fetchable:

```
git am docs/integration_round96/patches/0001-*.patch \
       docs/integration_round96/patches/0002-*.patch
```

If you take option 2 or 3, say so on PR110 so the integration branch can drop its copy rather than conflict with yours.

## What must not drift

- **`MANIFEST.json` changes are additive only.** Every existing `movie_sha256`, `movie_bytes` and `ground_truth_sha256` is byte-for-byte unchanged; the five `star_sha256` values are computed from the `.star` files exactly as already committed. No hash was regenerated and none was loosened.
- **`star_sha256` is a required schema field.** A manifest without it fails validation with exit 2 rather than silently skipping the STAR check. Control 8D pins that.
- **Canonical mode now requires the committed `.star` to exist**, symmetrically with how it already requires the ground-truth JSON. Any sandbox that runs `--canonical` must stage the `.star`; Controls 5 and 6 were updated for exactly this reason.
- **Normal (non-canonical) generation is unchanged** and still writes the `.star`.

## What this does not claim

The fix closes metadata drift that leaves the pixels untouched. It does not make the fixture set exhaustive: a semantically meaningful STAR edit that a maintainer deliberately commits, together with an updated digest, is still accepted — by design, since that is the documented maintenance path. The control proves the *silent* path is closed, not that every metadata change is judged.
