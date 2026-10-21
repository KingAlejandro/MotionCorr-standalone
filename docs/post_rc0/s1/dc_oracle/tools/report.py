#!/usr/bin/env python3
"""Regenerate review tables and the complete 540-comparison CSV from evidence."""
import collections,csv,json,pathlib,sys
s=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else pathlib.Path(__file__).resolve().parents[1]);r=s/'results';rows=json.load(open(r/'rows.json'));x=json.load(open(r/'summary.json'));assert len(rows)==60
arms=['Rprime','C_none','C_global','C_local','C_both','G_none','G_global','G_local','G_both'];names={'Rprime':"R′ (CPU double, both)",**{b+'_'+dc:('CPU float' if b=='C' else 'CUDA float')+', '+dc for b in ['C','G'] for dc in ['none','global','local','both']}}
f=lambda v:f'{v:.8g}'
lines=['# Full-census numerical-reference results','', 'R is CPU double with DC retained. Every table includes both e10216-01 grids unless explicitly labelled otherwise. S1 screen = product relRMSE ≥0.1; this is descriptive, not a scientific gate.','', '## Product and patch-set comparison, all 60','', '| Arm | Positive configs /60 | Movies any grid /30 | Accepted sets equal /60 | Median relRMSE | Worst relRMSE |','|---|---:|---:|---:|---:|---:|']
for arm in arms:
 a=x['arms'][arm]['all'];lines.append(f"| {names[arm]} | {a['positive_configs']} | {a['positive_movies']} | {a['accepted_set_equal']} | {f(a['product_relRMSE']['median'])} | {f(a['product_relRMSE']['worst'])} |")
lines+=['','## Native trajectory and applied local field, all 60','','All errors are vector magnitudes in original pixels. Median max/RMS are medians over the per-config maxima/RMS values. Local fields use full-precision applied coefficients, a 33×33 endpoint-inclusive normalized grid [-0.5,0.5]² and every integer frame z=0…N−1. A disabled local model contributes a zero applied field; active-model status is retained per row.','','| Arm | Global median max / RMS | Global worst max | Local median max / RMS | Local worst max |','|---|---:|---:|---:|---:|']
for arm in arms:
 a=x['arms'][arm]['all'];g,l=a['global_px'],a['local_field_native_px'];lines.append(f"| {names[arm]} | {f(g['median_max'])} / {f(g['median_rms'])} | {f(g['worst_max'])} | {f(l['median_max'])} / {f(l['median_rms'])} | {f(l['worst_max'])} |")
lines+=['','## Same errors excluding the two known failure configs','','| Arm | Global median max / RMS | Global worst max | Local median max / RMS | Local worst max | Median / worst relRMSE |','|---|---:|---:|---:|---:|---:|']
for arm in arms:
 a=x['arms'][arm]['other58'];g,l=a['global_px'],a['local_field_native_px'];p=a['product_relRMSE'];lines.append(f"| {names[arm]} | {f(g['median_max'])} / {f(g['median_rms'])} | {f(g['worst_max'])} | {f(l['median_max'])} / {f(l['median_rms'])} | {f(l['worst_max'])} | {f(p['median'])} / {f(p['worst'])} |")
lines+=['','## Exact McNemar against R-screen positives','','Cells are (both positive, baseline-only, conditioned-only, neither). Config p values treat rows as independent and are descriptive because the two grids are correlated. Movie sensitivity collapses the grids with “at least one positive”; movies within a collection can also be correlated. No positive-only selection or threshold changes.','','| Transition | Config cells | Config exact p | Movie cells | Movie exact p |','|---|---|---:|---|---:|']
for name,v in x['transitions'].items():lines.append(f"| {name} | {v['configs']['cells_both_Aonly_Bonly_neither']} | {f(v['configs']['exact_p_two_sided'])} | {v['movies_any_grid']['cells_both_Aonly_Bonly_neither']} | {f(v['movies_any_grid']['exact_p_two_sided'])} |")
lines+=['','## Family and grid screen counts versus R','','| Arm | 10216 p5 / p3 | 12963 p5 / p3 | Falcon 3 p5 / p3 |','|---|---:|---:|---:|']
for arm in arms:
 cells=[]
 for fam in ['e10216','e12963','e10474f3']:
  cells.append(' / '.join(str(sum(z['arms'][arm]['product']['relative_rmse']>=.1 for z in rows if z['movie'].startswith(fam+'-') and z['grid']==g)) for g in [5,3]))
 lines.append('| '+names[arm]+' | '+' | '.join(cells)+' |')
lines+=['','## CPU-versus-CUDA continuity screen, matched DC arms','','| DC arm | Positive configs /60 | Movies any grid /30 |','|---|---:|---:|']
for dc in ['none','global','local','both']:
 br=x['backend_continuity'];n=sum(z['arms'][dc]['relative_rmse']>=.1 for z in br);mv=len({z['movie'] for z in br if z['arms'][dc]['relative_rmse']>=.1});lines.append(f'| {dc} | {n} | {mv} |')
lines+=['','| Matching-DC backend transition | Config cells | Exact p | Movie cells | Exact p |','|---|---|---:|---|---:|']
for name,v in x['backend_transitions'].items():lines.append(f"| {name} | {v['configs']['cells_both_Aonly_Bonly_neither']} | {f(v['configs']['exact_p_two_sided'])} | {v['movies_any_grid']['cells_both_Aonly_Bonly_neither']} | {f(v['movies_any_grid']['exact_p_two_sided'])} |")
lines+=['','## e10216-01, retained in all counts','','Both grids share their global trajectory. These runs exhaust the global iteration budget; exit 0 does not imply convergence.','','| Arm | Last global increment RMSD | Max global gap vs R | p5 / p3 relRMSE vs R |','|---|---:|---:|---:|']
e={z['grid']:z for z in rows if z['movie']=='e10216-01'};rr=e[5]['arms']['Rprime']['divergence']['global_increment_rmsd']['reference'];lines.append(f'| R | {f(rr[-1])} | 0 | 0 / 0 |')
for arm in arms:
 a=e[5]['arms'][arm];inc=a['divergence']['global_increment_rmsd']['arm'];lines.append(f"| {names[arm]} | {f(inc[-1])} | {f(a['global_px']['max'])} | {f(a['product']['relative_rmse'])} / {f(e[3]['arms'][arm]['product']['relative_rmse'])} |")
lines+=['','## First-divergence classifications','','Every comparison has a retained first-integer-change and first >0.5 px candidate-event record (or an explicit absence). The table below summarizes the ≥0.1 product disagreements. The first event is iteration-major within a selected S1-relevant call, preferring global before local; smaller arithmetic/input errors can precede it. Same-integer witnesses have different samples and are not a same-sample scalar-fit defect. CUDA same-map tie-order differences are labelled separately.','','| Arm | Positive-comparison classifications |','|---|---|']
for arm in arms:
 c=collections.Counter(z['arms'][arm]['divergence']['classification'] for z in rows if z['arms'][arm]['product']['relative_rmse']>=.1);lines.append('| '+names[arm]+' | '+('; '.join(f'{k}: {v}' for k,v in sorted(c.items())) or 'none')+' |')
lines+=['','## All configurations','','Counts below are screen positives among the two grid rows, against R. Complete continuous measurements and provenance are in `census.csv` and `results/rows.json`.','','| Movie | R′ | CPU none/global/local/both | CUDA none/global/local/both |','|---|---:|---|---|']
for movie in sorted({z['movie'] for z in rows}):
 z=[q for q in rows if q['movie']==movie];count=lambda a:sum(q['arms'][a]['product']['relative_rmse']>=.1 for q in z);lines.append(f"| {movie} | {count('Rprime')} | "+'/'.join(str(count('C_'+a)) for a in ['none','global','local','both'])+' | '+'/'.join(str(count('G_'+a)) for a in ['none','global','local','both'])+' |')
(s/'tables.md').write_text('\n'.join(lines)+'\n')
with (s/'census.csv').open('w') as fh:
 w=csv.writer(fh,lineterminator="\n");w.writerow(['movie','grid','arm','relRMSE_vs_R','global_max_px','global_rms_px','local_field_native_max_px','local_field_native_rms_px','accepted_set_equal','active_local_model','known_e10216_01','first_divergence_class'])
 for row in rows:
  for arm in arms:
   q=row['arms'][arm];w.writerow([row['movie'],row['grid'],arm,q['product']['relative_rmse'],q['global_px']['max'],q['global_px']['rms'],q['local_field_native_px']['max'],q['local_field_native_px']['rms'],q['accepted_set_equal'],q['active_local'],row['movie']=='e10216-01',q['divergence']['classification']])
print('tables: 60 configs, 540 comparisons')
