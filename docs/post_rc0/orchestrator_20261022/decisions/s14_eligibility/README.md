# Provisional S1.4 data eligibility inventory

Metadata-only preparation, **not an approved cohort, complete acquisition audit,
source freeze or scientific result**. No movie/gain/particle/map download, image decode, raw payload hash,
reconstruction or refinement was performed. No new scientific outcomes were
opened. The current S1 sweep manifest was read as metadata, and a single read-only
filesystem `stat` query checked the explicitly listed movie/gain paths plus the
conventional per-ID input-STAR locations. No unrelated project tree was scanned.

At 20:06:54 UTC, 22 October 2026, the manifest's 114 movie files (24 tutorial and
10 each in nine named families) were present and their byte sizes matched.
Their 114 distinct recorded SHA256 values are assertions in the snapshot, **not
freshly verified content identities**. Geometry and acquisition values below are
also recipe assertions, not fresh header/archive verification. The old manifest's
`inventory.staged_distinct_paths` counts are stale relative to the current path
probe and must not be used as the present acquired count. Presence/size alone
neither proves integrity nor establishes 114 independent scientific replicates.

| Family | Movie files observed / recipe rows | Dose provenance in recipe | Scientific admission now |
| --- | --- | --- | --- |
| tutorial | 24/24 | Historical tutorial value | Developmental/unblinded; not a new holdout |
| e10028 | 10/10 | Placeholder | Incomplete |
| e10164 | 10/10 | Placeholder | Incomplete |
| e10216 | 10/10 | Placeholder | Incomplete |
| e10361 | 10/10 | Recipe total dose divided by frames | Incomplete; not independently acquisition-verified |
| e10441 | 10/10 | Recipe accession XML value | Incomplete; not independently acquisition-verified |
| e10474f3 | 10/10 | Placeholder | Incomplete |
| e10474f4 | 10/10 | Placeholder | Incomplete |
| e10641 | 10/10 | Placeholder | Incomplete |
| e12963 | 10/10 | Nominal total / grouped frames, grouping allocation not established | Incomplete |

The stat command returned **123** for missing requested paths, retained in raw
stdout/stderr: all 26 are conventional `sweep/inputs/<id>/movies.star` paths,
not raw movies. These locations were constructed for this probe, not promised
for every ID by the manifest. Some prior campaigns use `dc-oracle/inputs`
instead; absence here is not an assertion that their actual command input is
missing. The 88 conventional STARs and four distinct supplied gain paths are
present. The individual processing/exposure and complete actual-argv/input path
map still need reconciliation before selecting a cohort.

A bounded directory-presence probe found the historical tutorial Refine3D/job019
and MaskCreate/job020 project locations. That is not verification of particle
accounting, maps, halfsets, matched settings, or mask identity. Independent-family
downstream inputs were **not searched** by this probe, so they are unknown rather
than declared absent. No archived refinement/FSC endpoint was read.

`eligibility.json` retains every exact movie ID/path, declared hash/size, fresh
stat result, recipe geometry and missing conventional STAR. Licence/session/
specimen/gain-transform provenance, required dose/grouping validation, complete
matched particle/halfset/mask/settings manifest, and outcome-exposure audit remain
unverified for the new study. All families are therefore marked INCOMPLETE and
not admitted; this does not claim the data cannot become usable.

Before M6: resolve those fields using acquisition evidence, reconcile actual
input STAR paths without silently changing gains/dose, distinguish already used
diagnostic/challenge cohorts from untouched scientific outcomes, freeze the
selection rule and independent forward-harm/operating-characteristic design, and
complete independent protocol review. No choice can rely on candidate-favourable
scientific outcomes. Relevant policy/truth criteria, explicit C2 freeze and M6
approval still precede held-out analysis. No larger acquisition or new scientific
run is implicitly authorized by this inventory.

The [official archive metadata cross-check](archive_metadata/README.md) corroborates
some recipe fields and records an unresolved EER rendering/grouping/pixel-size
mapping for EMPIAR-12963. It changes no campaign options or admission verdict.
