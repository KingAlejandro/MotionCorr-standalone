#!/bin/bash
set -euo pipefail
W=/mnt/clathrin/alex-motioncorr-214
export PATH=$W/tools/usr/bin:/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID
cd "$W"
flock -n /tmp/motioncorr-bench.lock true
exec 9>/tmp/motioncorr-gpu0-correctness.lock
flock 9
if nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q "$CUDA_VISIBLE_DEVICES"; then exit 80; fi
BASE=/mnt/clathrin/alex-motioncorr-rc0/W-QF/build-nvcomp/motioncorr
sha256sum "$BASE" > logs/native-baseline.sha256
printf '2e00e0e8fb75aafaf23f15a3c2a142c7d35b6e30477d594244ecba495a5bb6b3  %s\n' "$BASE" | sha256sum -c -
for codec in bz2 xz zst; do
 set +e
 taskset -c 88-95 /home/alex/.mc-venv/bin/python3 src/tests/test_compressed_mrc_status.py --binary "$BASE" --codec "$codec" --gpu 0 --work "$W/native-unfixed-$codec" > "logs/native-unfixed-$codec.log" 2>&1
 rc=$?
 set -e
 [ "$rc" = 1 ] || exit 81
 taskset -c 88-95 /home/alex/.mc-venv/bin/python3 src/tests/test_compressed_mrc_status.py --binary "$W/build-nvcomp/motioncorr" --baseline-binary "$BASE" --codec "$codec" --gpu 0 --work "$W/native-identity-$codec" > "logs/native-identity-$codec.log" 2>&1
 done
python3 - <<'PY2'
from pathlib import Path
p=Path('src/docs/rc0/qual_mrc_staging/synth_mrc_matrix.py')
s=p.read_text().replace('ROOT = Path(__file__).resolve().parents[3]', 'ROOT = Path("/mnt/clathrin/alex-motioncorr-214/src")')
s=s.replace('expect_ok = not (codec == "bz2" and vname == "native")', 'expect_ok = True  # Native pbzip2 installed in task scratch.')
Path('replay_204.py').write_text(s)
PY2
diff -u src/docs/rc0/qual_mrc_staging/synth_mrc_matrix.py replay_204.py > logs/replay_204.patch || [ "$?" = 1 ]
taskset -c 88-95 /home/alex/.mc-venv/bin/python3 replay_204.py --binary "$W/build-nvcomp/motioncorr" --gpu 0 --work "$W/replay204" --out "$W/replay204.json" --section compressed --keep-outputs > logs/replay204.log 2>&1
python3 - <<'PY2'
import json
from pathlib import Path
for codec in ('bz2','xz','zst'):
 root=Path('native-identity-'+codec)
 data=json.loads((root/'results.json').read_text())
 for r in data['records']:
  if r['rc'] or r['case'].endswith('-baseline'): continue
  text=(root/r['case']/'out/movie_mrc.log').read_text()
  assert 'Computing full-frame Fourier transforms (CUDA in-VRAM)' in text, (codec,r['case'])
 print(codec, 'native in-VRAM witnesses verified')
d=json.loads(Path('replay204.json').read_text())
assert all(r['pass'] for key in ('compressed','damaged') for r in d[key])
print('replay204',len(d['compressed']),len(d['damaged']),'PASS')
PY2
echo EXTRA_DONE
