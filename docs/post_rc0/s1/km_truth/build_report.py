#!/usr/bin/env python3
"""Render the compact, standalone census view from committed numerical evidence."""
from pathlib import Path
import json
import html
ROOT=Path(__file__).resolve().parent
s=json.loads((ROOT/'SUMMARY.json').read_text())
n=json.loads((ROOT/'native_v2_metrics.json').read_text())
# Keep the interactive artifact small; full per-frame and per-seed fields remain in JSON.
dictkeys=['condition','arm','median_field_px','median_field_angstrom','global_nonconverged','local_disabled','field_distance_failures','invalid_sampling','median_global_rms_px','median_local_rms_px']
rows=[{k:r[k] for k in dictkeys} for r in s['table']]
pairs=[dict(condition=r['condition'],arm=r['candidate'],**r['metrics']['field_px']) for r in s['paired']]
points=[[r['condition'],r['seed'],r['arm'],r['field_px']['rms']] for r in s['rows']]
refs=[]
for c in dict.fromkeys(r['condition'] for r in rows):
 for a in dict.fromkeys(r['arm'] for r in rows):
  z=[r for r in s['double_reference_distance'] if r['condition']==c and r['arm']==a]
  if z:refs.append([c,a,max(r['field_distance']['px']['max'] for r in z)])
data=json.dumps(dict(rows=rows,pairs=pairs,points=points,refs=refs,native=n),separators=(',',':'))
page='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Motion-truth census</title><style>
*{box-sizing:border-box}body{margin:0;color:var(--foreground,#202326);font:14px/1.5 var(--font-sans,system-ui)}
p{margin:12px 0}a{color:var(--accent,#2165a4)}label{display:inline-flex;align-items:center;gap:8px;margin:0 16px 10px 0}select{font:inherit;color:inherit;background:var(--background,white);border:1px solid var(--border,#bbb);padding:5px;border-radius:6px}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:12px}th,td{padding:7px 5px;border-bottom:1px solid var(--border,#ddd);text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{font-weight:600}tr.ref{background:var(--muted,#eee)}.small{font-size:12px;color:var(--muted-foreground,#626970)}.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px}b{font-weight:650}svg{width:100%;height:220px}details{margin:18px 0}summary{cursor:pointer;font-weight:600}.result{font-size:15px;margin:16px 0}.key{color:var(--accent,#2165a4)}
</style><p><b>Motion truth · 100 movies · 900 native arms</b><br><span class="small">40 frames; 4096² / 5760×4092; ten Poisson seeds per condition. All numbers below measure truth error on a fixed 129² lattice.</span></p>
<label>Condition <select id="condition"></select></label><label>Units <select id="unit"><option value="px">px</option><option value="angstrom">Å</option></select></label>
<div id="finding" class="result"></div><div class="scroll"><table><thead><tr><th>Arm</th><th>RMS</th><th>P95</th><th>Max</th><th>Global nonconv.</th><th>Max vs double*</th></tr></thead><tbody id="body"></tbody></table></div>
<p class="small">RMS/P95/max columns are medians across ten per-seed vector statistics. Nonconvergence is a seed count out of ten. *Worst field distance to the double reference across all ten seeds, in selected units. Double CCF retains float movie spectra and feedback.</p>
<svg id="plot" viewBox="0 0 700 220" role="img" aria-label="Per-seed field RMS for CPU none, CPU both and double reference"></svg><div class="legend"><span style="color:#a34d29">● CPU none</span><span style="color:#3472aa">● CPU both</span><span style="color:#458258">● CPU double CCF</span></div>
<div id="paired"></div><p class="small">Exact two-sided sign tests use ten paired seed RMS errors; |delta|≤1e−9 px counts as a tie. Negative delta improves. Labels use exploratory p&lt;.05; neutral/mixed does not establish equivalence. Multiple conditions/arms were examined.</p>
<details><summary>Native #267 controls on main</summary><p class="small">128×96×5; main 36913740, fixture/checker 88b34ae0. Original checker outcomes retained. Finite out-of-ROI candidates receive independent field-only statistics here; no gate or ROI was relaxed.</p><div class="scroll"><table><thead><tr><th>Backend / case</th><th>RMS</th><th>P95</th><th>Max</th><th>Checker</th></tr></thead><tbody id="native"></tbody></table></div></details>
<p class="small">Historical km_local_noisy remains an accuracy FAIL characterization. Frequency transfer and held-out CTF/FSC science are unrun; field agreement is not published-image qualification. <a href="https://github.com/KingAlejandro/MotionCorr-standalone/pull/269">Test-only PR #269</a> · <a href="https://github.com/KingAlejandro/MotionCorr-standalone/blob/test/realistic-motion-truth/docs/post_rc0/s1/km_truth/README.md">Evidence and limitations</a></p>
<script>const DATA=__DATA__;
const conditions=[...new Set(DATA.rows.map(x=>x.condition))],labels={dose1:'Dose 1 e/px/frame',dose05:'Dose 0.5',dose2:'Dose 2',dose4:'Dose 4',outmodel:'Out-of-model motion',nonsquare:'Nonsquare 5760 × 4092',pedestal0:'Pedestal 0',pedestal32:'Pedestal 32',contrast025:'Amplitude ×0.25',contrast4:'Amplitude ×4'};
const sel=document.getElementById('condition'),unit=document.getElementById('unit');conditions.forEach(c=>sel.add(new Option(labels[c],c)));sel.value='pedestal32';
const fmt=x=>x===null?'—':Math.abs(x)<.00001&&x!==0?x.toExponential(2):Number(x).toFixed(5);
function draw(){let c=sel.value,u=unit.value,k=u==='px'?1:.885;let rr=DATA.rows.filter(r=>r.condition===c);let pp=DATA.pairs.filter(r=>r.condition===c);document.getElementById('body').innerHTML=rr.map(r=>{let m=r[u==='px'?'median_field_px':'median_field_angstrom'];let ref=DATA.refs.find(z=>z[0]===c&&z[1]===r.arm);return `<tr class="${r.arm==='cpu-double'?'ref':''}"><td>${r.arm}</td><td>${fmt(m.rms)}</td><td>${fmt(m.p95)}</td><td>${fmt(m.max)}</td><td>${r.global_nonconverged}/10</td><td>${ref?fmt(ref[2]*k):'reference'}</td></tr>`}).join('');
let cpu=pp.find(x=>x.arm==='cpu-both'),gpu=pp.find(x=>x.arm==='cuda-both');document.getElementById('finding').textContent=`Both stages vs unconditioned: CPU ${cpu.interpretation}; CUDA ${gpu.interpretation}.`;
document.getElementById('paired').innerHTML='<p><b>Paired RMS change (both stages − none)</b></p><div class="scroll"><table><thead><tr><th>Backend</th><th>Median Δ '+(u==='px'?'px':'Å')+'</th><th>Wins/losses/ties</th><th>Sign p</th></tr></thead><tbody>'+[cpu,gpu].map(p=>`<tr><td>${p.arm.split('-')[0]}</td><td>${fmt(p.median_delta_px*k)}</td><td>${p.wins}/${p.losses}/${p.ties}</td><td>${p.sign_test_two_sided_p.toFixed(5)}</td></tr>`).join('')+'</tbody></table></div>';
const series=['cpu-none','cpu-both','cpu-double'],colors=['#a34d29','#3472aa','#458258'];let points=DATA.points.filter(p=>p[0]===c&&series.includes(p[2]));let low=Math.min(...points.map(p=>p[3]*k)),high=Math.max(...points.map(p=>p[3]*k));let pad=Math.max((high-low)*.12,.001);low=Math.max(0,low-pad);high+=pad;let Y=v=>180-(v-low)/(high-low)*155,X=s=>70+s*65;let svg=`<line x1="70" y1="180" x2="655" y2="180" stroke="currentColor" opacity=".35"/><text x="4" y="26" fill="currentColor" font-size="11">RMS ${u==='px'?'px':'Å'}</text>`;for(let t=0;t<4;t++){let v=low+(high-low)*t/3,y=Y(v);svg+=`<line x1="70" y1="${y}" x2="655" y2="${y}" stroke="currentColor" opacity=".12"/><text x="4" y="${y+4}" fill="currentColor" font-size="11">${v.toFixed(3)}</text>`}for(let s=0;s<10;s++)svg+=`<text x="${X(s)}" y="201" text-anchor="middle" fill="currentColor" font-size="11">${s}</text>`;svg+='<text x="665" y="201" fill="currentColor" font-size="11">seed</text>';series.forEach((a,i)=>{let z=points.filter(p=>p[2]===a).sort((a,b)=>a[1]-b[1]);svg+=`<polyline points="${z.map(p=>X(p[1])+','+Y(p[3]*k)).join(' ')}" fill="none" stroke="${colors[i]}" stroke-width="1.5" opacity=".7"/>`;z.forEach(p=>svg+=`<circle cx="${X(p[1])}" cy="${Y(p[3]*k)}" r="3.5" fill="${colors[i]}"><title>${a}; seed ${p[1]}; RMS ${fmt(p[3]*k)}</title></circle>`)});document.getElementById('plot').innerHTML=svg;
document.getElementById('native').innerHTML=DATA.native.map(r=>{let m=r[u==='px'?'field_px':'field_angstrom'];return `<tr><td>${r.backend} / ${r.case}</td><td>${fmt(m.rms)}</td><td>${fmt(m.p95)}</td><td>${fmt(m.max)}</td><td>${r.original_checker_status.replace('INPUT_ERROR_OUTSIDE_ROI','ROI ERROR')}</td></tr>`}).join('');}
sel.onchange=draw;unit.onchange=draw;draw();console.log('tables',DATA.rows.length,'seeds',DATA.points.length,'native',DATA.native.length);
</script>'''.replace('__DATA__',data)
(ROOT/'report.html').write_text(page)
