# Publication checkpoint, 23 October 2026

This is an incomplete experimental draft, not an M3 recommendation or a merge
request. Read the qualified frozen Tier B packet first:
[analysis_B_pass3_20261023/README.md](../analysis_B_pass3_20261023/README.md).
Its independent review reproduced the arithmetic; that does not qualify the
whole native campaign, cost, science or the proposed successor worker.

The older top-level M3 wording overstated the pedestal result. Both-stage DC
conditioning reduces descriptive pedestal error, but 9/10 pedestal32 field
gates still FAIL per backend in the frozen Tier B snapshot. No nonzero Tier A
case passes its field gate in any arm. No arm is selected for adoption.
Original numerical records, categories and failed iterations are unchanged.

`resource_join.py` reads only retained metadata and archive member names, without
extraction, remote access or new endpoint evaluation. Its deterministic
`RESOURCE_JOIN.json` binds both input artifacts and the script by SHA-256. All
54 recorded FOREIGN_OBSERVED IDs belong to Tier C; none is among the 736 frozen
Tier B evaluation records. This checks the recorded overlap set only: before
and after snapshots do not establish continuous exclusive occupancy. Tier C
remains incomplete; its resource-affected records retain their original exits
and labels. No timing comparison is qualified.

```
/Users/alex.konstantinov/.local/bin/python3 -I -B resource_join.py > RESOURCE_JOIN.json
```

Worker v5 at `1a62f0f94bded08279d879caed6482c817843833` is under independent
Sonnet R4 source/control review. Its live-worker mock suite is UNRUN because
local load exceeded the frozen admission bound; synthetic checks do not replace
it. Linux subreaper execution and GPU use are UNRUN. The namespace reader is
unimplemented; evaluation of resumed namespaces is blocked. The user requested
CPU and reviews only. No GPU resume is authorized or launched by this packet.
