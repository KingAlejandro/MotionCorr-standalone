set -u
W=/home/alex/mc-release-20261002; PY=/home/alex/mc-env/bin/python3
P=$W/prof; A=$W/nsysan; O=$W/report; mkdir -p $O/charts $O/data
cd $W
echo "=== per-capture extraction (one capture per JSON, no cross-run arithmetic) ==="
for t in gpu-a1_base gpu-a6_final host-a1_base host-a6_final flame-a1_base flame-a6_final; do
  [ -f $P/$t/prof.sqlite ] || { echo "MISSING $t"; continue; }
  $PY prof_json.py $P/$t/prof.sqlite $O/data/prof-$t.json
done
echo
echo "=== flame graphs (sampled captures only) ==="
for a in a1_base a6_final; do
  [ -f $P/flame-$a/prof.sqlite ] || continue
  $PY $A/folded.py $P/flame-$a/prof.sqlite $O/data/flame-$a.folded main 2>&1 | tail -2
  n=$(wc -l < $O/data/flame-$a.folded)
  if [ "$n" -gt 0 ]; then
    $PY $A/mkflame.py $O/data/flame-$a.folded $O/charts/flame-$a.svg "MotionCorr $a - CPU samples, 24 movies (nsys --sample=process-tree --backtrace=fp)"
    echo "flame-$a: $n folded stacks -> svg"
  else echo "flame-$a: NO SAMPLES (host sampling unavailable)"; fi
done
echo
echo "=== stage table: base vs final, each from its OWN nvtx+osrt capture ==="
$PY - <<'PYX'
import json,pathlib
O=pathlib.Path('/home/alex/mc-release-20261002/report')
try:
    b=json.loads((O/'data/prof-host-a1_base.json').read_text())['stages']
    f=json.loads((O/'data/prof-host-a6_final.json').read_text())['stages']
except FileNotFoundError as e: raise SystemExit('missing host capture: %s'%e)
keys=sorted(set(b)|set(f), key=lambda k:-max(b.get(k,{}).get('union_s',0),f.get(k,{}).get('union_s',0)))
rows=[{'stage':k,'base':b.get(k,{}).get('union_s',0.0),'final':f.get(k,{}).get('union_s',0.0),
       'base_n':b.get(k,{}).get('instances',0),'final_n':f.get(k,{}).get('instances',0)} for k in keys]
(O/'data/stages.json').write_text(json.dumps(rows,indent=2))
print(f"{'stage':34s} {'base s':>9s} {'final s':>9s} {'delta s':>9s}")
for r in rows[:20]:
    print(f"{r['stage'][:34]:34s} {r['base']:9.3f} {r['final']:9.3f} {r['base']-r['final']:+9.3f}")
PYX
echo
echo "=== device occupancy table ==="
$PY - <<'PYX'
import json,pathlib
O=pathlib.Path('/home/alex/mc-release-20261002/report'); out=[]
for arm in ('a1_base','a6_final'):
    d=json.loads((O/f'data/prof-gpu-{arm}.json').read_text())
    dv=d['device']
    out.append({'arm':arm,'span':d['traced_span_s'],'kernel':dv['kernel_union_s'],'copy':dv['copy_union_s'],
                'launches':dv['launches'],'memcpys':dv['memcpys'],'h2d_GB':dv['h2d_bytes']/1e9,'d2h_GB':dv['d2h_bytes']/1e9})
    print(f"{arm:10s} span={d['traced_span_s']:7.3f}s kernel={dv['kernel_union_s']:6.3f}s copy={dv['copy_union_s']:6.3f}s "
          f"busy={100*dv['busy_union_s']/d['traced_span_s']:5.1f}% launches={dv['launches']} H2D={dv['h2d_bytes']/1e9:.2f}GB")
(O/'data/gpu.json').write_text(json.dumps(out,indent=2))
PYX
echo
echo "=== charts ==="
cp $W/campaign/runs.json $W/campaign/provenance.json $O/data/
LBL="source perf/single-gpu-pools 054ed6d vs base b4536e2 | 4GPUs A100-80GB GPU-eddb42fe | CUDA 12.8, nvCOMP 5.3.0.16 | Release | taskset 64-71, OMP_NUM_THREADS=6 | THP madvise"
$PY mkcharts.py arms   $O/data/runs.json   $O/charts/arms.svg   --label "$LBL"
$PY mkcharts.py mem    $O/data/runs.json   $O/charts/mem.svg    --label "$LBL"
$PY mkcharts.py stages $O/data/stages.json $O/charts/stages.svg --label "$LBL  |  capture: --trace=nvtx,osrt"
$PY mkcharts.py gpu    $O/data/gpu.json    $O/charts/gpu.svg    --label "$LBL  |  capture: --trace=cuda,nvtx"
echo "ANALYZE-DONE"
