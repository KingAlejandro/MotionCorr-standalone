# SPDX-License-Identifier: GPL-2.0-or-later
# Presentation-only supplement. Frozen summaries/evaluations are not rewritten.
from pathlib import Path
import json,hashlib,statistics,collections,sys
SRC=Path(sys.argv[1]).resolve()
OUT=Path(sys.argv[2]).resolve()
OUT.mkdir(exist_ok=False)
j=json.loads((SRC/'tierB.json').read_text());evaluations=[json.loads(p.read_text()) for p in sorted((SRC/'eval/B').glob('*.json'))]
counts=collections.Counter(x['status'] for x in evaluations);assert counts=={'EVALUATED':734,'CONTROL_ONLY':2}
assert len(j['rows'])==80 and len(j['pairs'])==240 and len(j['regressions'])==878
header='''# Qualified presentation of the frozen Tier B snapshot

DRAFT partial descriptive analysis. Source3eee0a4b; snapshot22:44:59Z. This supplement changes presentation only and preserves the frozen raw tables/JSON. Selected736 records comprise734 EVALUATED experiments and2 CONTROL_ONLY plain CUDA records;68 jobs excluded at freeze. The two CPU plain records were excluded. Plain-vs-none byte controls are UNRUN for Tier B. All734 experiment sampling statuses are VALID. No adoption, science, performance or full-campaign acceptance.

Each complete cell has10 matched noise seeds on one fixed scene/motion field. Several conditions are affine copies of related noise draws; metrics/backends are dependent. Nominal labels use the frozen unadjusted sign rule with no effect-size floor or calibrated none-vs-none CUDA noise. They are descriptive labels, not31 independent findings. Partial-arm medians use unequal seed cohorts and must not be compared as arm effects. The separate common-seed panel below is descriptive only. UNRUN cells display UNRUN throughout.

## Per-arm descriptive metrics

| Condition | Backend | Arm | Evidence | Evaluated / expected | RMS px | P95 px | Worst max px | Transfer | Global nonconv | Local disabled | Outside ROI | Field FAIL | Failure union |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
'''
lines=[header]
def fmt(v):return 'UNRUN' if v is None else f'{v:.6g}'
for r in j['rows']:
 n=r['n'];state='COMPLETE' if n==10 else 'PARTIAL: unmatched cohort' if n else 'UNRUN';f=r['failures']
 fields=[r['condition'],r['backend'],r['arm'],state,f'{n}/10']
 fields += [fmt(r.get(k)) if n else 'UNRUN' for k in ['median_rms_px','median_p95_px','worst_max_px','median_transfer']]
 fields += [f'{f[k]}/{n}' if n else 'UNRUN' for k in ['global_nonconverged','local_disabled','outside_roi','field_distance_fail','union']]
 lines.append('| '+' | '.join(fields)+' |\n')
lines.append('\n## Frozen paired comparisons, all 240 retained\n\nLabels and p-values are unadjusted exploratory results with no magnitude floor. Tests cover RMS, maximum field error and two transfer metrics, not every descriptive endpoint. Incomplete cells do not supply a complete10-seed inference.\n\n| Condition | Backend | Arm vs none | Metric | Matched pairs / expected | Median delta | Exact p | Nominal label |\n| --- | --- | --- | --- | ---: | ---: | ---: | --- |\n')
for r in j['pairs']:
 n=r['pairs'];label=r['category'];label='nominal '+label if label in ['improves','harms'] else label
 fields=[r['condition'],r['backend'],r['arm'],r['metric'],f'{n}/10',fmt(r.get('median_delta')) if n else 'UNRUN',fmt(r.get('sign_p')) if n else 'UNRUN',label]
 lines.append('| '+' | '.join(fields)+' |\n')
# Common-seed descriptive supplement for the sole partial evaluated condition.
records={(e['group'],e['arm']):e for e in evaluations if e['status']=='EVALUATED' and e['backend']=='cpu' and e['group'].startswith('outmodel-')}
arms=['none','global','local','both'];groups={a:{g for g,b in records if a==b} for a in arms};common=sorted(set.intersection(*(groups[a] for a in arms)));assert common==['outmodel-s00','outmodel-s01','outmodel-s02']
common_rms={a:statistics.median(records[(g,a)]['truth']['field']['px']['rms'] for g in common) for a in arms}
lines.append('\n## Partial outmodel CPU, common seeds only\n\nThe original per-arm cohorts have4/4/3/3 observations. On common seeds00–02 only, the medians below avoid that cohort mismatch. No new hypothesis test or acceptance gate is defined.\n\n| Arm | Common groups | Median RMS px |\n| --- | --- | ---: |\n')
for a,v in common_rms.items():lines.append(f'| {a} | {", ".join(common)} | {v:.6f} |\n')
lines.append('''
## Interpretation and limits

- Frozen category counts:30 nominal improves,1 nominal harms,185 neutral/mixed,12 IN_PROGRESS,12 UNRUN. All878 per-seed regressions remain in the original JSON;685 are below1e-3 in their metric units. Magnitudes are descriptive, not a newly adopted floor. Without correctness replicates, small CUDA deltas cannot be attributed to arm effects versus run variation.
- The single harms label is outmodel CUDA global RMS: median+2.664e-5px on a roughly1.04px field,9 losses/1 win,p=.021484375,no failure transition. No calibrated harm claim follows.
- At n10 the minimum two-sided sign p is.001953125. None survives Bonferroni across216 complete comparisons. The reviewer reports21 BH q<.05 entries; dependence assumptions are unvalidated, so no adjusted-inference conclusion is adopted. Fixed-scene/correlated conditions do not by themselves prove violation of every positive-dependence condition. The hypothetical independent-all-null expected4.6 nominal hits is not this experiment's calibrated null model.
- Pedestal32 both improves the descriptive medians and global/local convergence counts. For EACH backend, none→both global nonconvergence10→0, local-disabled10→0, field-distance FAIL10→9, failure union10→9. The union's fixed1/new0 hides the component changes;9/10 field failures remain. Local-only has real per-seed regressions and is mixed.
- Seed draws vary Poisson noise, not scene or motion-field identity. Results do not generalize to other scenes/motions or held-out science. No none-vs-none correctness replicate exists here. Timing/cost and Tier C are not evaluated by this snapshot.
- Frozen failure handling has a latent issue for non-EVALUATED records (review F8); none occurs among these734 experiment records. A separately versioned fix is required before a full-campaign summary, without changing this receipt. There is no adoption-ready M3 packet.
''')
(OUT/'TABLES_QUALIFIED.md').write_text(''.join(lines))
(OUT/'PRESENTATION.json').write_text(json.dumps({'source_summary_sha256':hashlib.sha256((SRC/'tierB.json').read_bytes()).hexdigest(),'record_composition':dict(counts),'row_count':80,'pair_count':240,'regressions_retained_in_frozen_summary':878,'common_outmodel_cpu_groups':common,'common_outmodel_cpu_rms_px':common_rms,'changes':'Presentation only. UNRUN marked explicitly; nominal labels qualified; no frozen calculation/category/gate changed.'},indent=2)+'\n')
print(json.dumps({'composition':dict(counts),'common_rms':common_rms,'rows':80,'pairs':240}))
