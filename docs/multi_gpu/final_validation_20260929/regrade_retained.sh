#!/usr/bin/env bash
# CPU-only regrading of existing native products. No CUDA binary or GPU query.
set -euo pipefail
set -x
ROOT=${1:?scratch root}
SRC="$ROOT/src"
RUN=/home/alex/mc-i53-native-20260928/work
REF=/home/alex/mc-i53-gpu/run/serialG
PY="$HOME/.mc-venv/bin/python3"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
date -Is
hostname
ps -p $$ -o pid,ppid,lstart,args
grep Cpus_allowed_list /proc/$$/status
numactl --show
sha256sum "$ROOT/source.tar.gz" "$SRC/tools/multi_gpu/compare24.py" "$SRC/tools/multi_gpu/merge_workers.py" "$SRC/tools/compare_motioncorr.py"
sha256sum "$RUN/native/status.json" "$RUN/native/shards/shard_manifest.json"
"$PY" "$SRC/tools/multi_gpu/merge_workers.py" \
  --manifest "$RUN/native/shards/shard_manifest.json" \
  --workers "$RUN/native/w0" "$RUN/native/w1" --status "$RUN/native/status.json" \
  --out "$ROOT/merged" --report "$ROOT/merge_report.json"
"$PY" "$SRC/tools/multi_gpu/compare24.py" --ref "$REF" --test "$ROOT/merged" \
  --tool "$SRC/tools/compare_motioncorr.py" \
  --manifest "$RUN/native/shards/shard_manifest.json" --out "$ROOT/exact"
cp -a "$ROOT/exact" "$ROOT/reuse"
"$PY" "$SRC/tools/multi_gpu/compare24.py" --ref "$REF" --test "$ROOT/merged" \
  --tool "$SRC/tools/compare_motioncorr.py" \
  --manifest "$RUN/native/shards/shard_manifest.json" --out "$ROOT/reuse" --reuse
"$PY" - "$ROOT" "$RUN" "$REF" <<'PY'
import hashlib, json, os, pathlib, shutil, subprocess, sys
root, run, ref = map(pathlib.Path, sys.argv[1:])
src = root / 'src'
manifest = run / 'native/shards/shard_manifest.json'
summary = json.loads((root/'exact/exact_summary.json').read_text())
assert (summary['n_expected'], summary['n_compared'], summary['passed'], summary['failed']) == (24,24,24,0)
assert len(list((root/'exact').glob('*.origin.json'))) == 24

# Edit only our newly staged copy, preserving size/mtime. Never change native originals.
shutil.copytree(root/'exact', root/'reuse_content_mutant')
victim = next((root/'merged').rglob('*.mrc'))
st = victim.stat()
with victim.open('r+b') as fh:
    fh.seek(1024); original = fh.read(1); fh.seek(1024); fh.write(bytes([original[0]^1]))
os.utime(victim, ns=(st.st_atime_ns, st.st_mtime_ns))
args = [sys.executable, str(src/'tools/multi_gpu/compare24.py'), '--ref', str(ref),
        '--test', str(root/'merged'), '--tool', str(src/'tools/compare_motioncorr.py'),
        '--manifest', str(manifest), '--out', str(root/'reuse_content_mutant'), '--reuse']
try:
    rc = subprocess.run(args).returncode
    assert rc == 1, f'same-size/same-mtime native content edit was reused: {rc}'
finally:
    with victim.open('r+b') as fh:
        fh.seek(1024); fh.write(original)
    os.utime(victim, ns=(st.st_atime_ns, st.st_mtime_ns))
print('NATIVE_CONTENT_REUSE_CONTROL=PASS')

# Regrade every retained MRC, including decorated products, against the serial arm.
expected = {p.relative_to(ref) for p in ref.rglob('*.mrc') if p.name != 'gain.mrc'}
actual = {p.relative_to(root/'merged') for p in (root/'merged').rglob('*.mrc') if '_workers' not in p.parts}
assert actual == expected, (sorted(expected-actual), sorted(actual-expected))
reports = root/'all_mrc'; reports.mkdir()
for i, rel in enumerate(sorted(expected)):
    cp = subprocess.run([sys.executable, str(src/'tools/compare_motioncorr.py'),
                         '--ref-mrc', str(ref/rel), '--test-mrc', str(root/'merged'/rel),
                         '--gate', 'exact', '--json-out', str(reports/f'{i:03d}.json')],
                        capture_output=True, text=True)
    assert cp.returncode == 0, (str(rel), cp.stdout, cp.stderr)
record = {'tool_source':'75a6296', 'native_source':'a48c7f5', 'fresh_gpu_compute':False,
          'primary_pairs':24, 'all_mrc_pairs':len(expected), 'content_reuse_negative':'PASS',
          'aggregate_rerun':False, 'cpu_masks':'110-111', 'numerical_gate':'exact'}
(root/'regrade_summary.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record))
PY
date -Is
echo RETAINED_REGRADE_PASS
