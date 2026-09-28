#!/usr/bin/env bash
set -euo pipefail
exec 200>/tmp/motioncorr-issue96-cpu-validation.lock
flock -w 1200 200
cd "$HOME/mc-pr103-fix-433f04e"
cp evidence/compat-controls.log evidence/compat-controls-unforced.log
exec > >(tee evidence/compat-controls.log) 2>&1
date -Is
git rev-parse HEAD
numactl --show
grep Cpus_allowed_list /proc/self/status
source "$HOME/.mc-venv/bin/activate"
printf '\000\000\000\000' > evidence/bad-header.tiff
mkdir -p evidence/legacy-include
for name in tiffio.h tiffvers.h; do
  printf '#include_next <%s>\n#undef TIFFLIB_AT_LEAST\n#define TIFFLIB_AT_LEAST(major, minor, micro) 0\n' "$name" > "evidence/legacy-include/$name"
done
cmake -S . -B build-legacy -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON -DCMAKE_CXX_FLAGS="-I$PWD/evidence/legacy-include"
cmake --build build-legacy -j 16
sha256sum build-legacy/motioncorr
ctest --test-dir build-legacy --output-on-failure
for mode in modern legacy; do
  builddir=build
  flags=()
  if [ "$mode" = legacy ]; then builddir=build-legacy; flags=(-I"$PWD/evidence/legacy-include" -DEXPECT_LEGACY_TIFF); fi
  g++ -std=c++17 -O2 -fopenmp -pthread -I. "${flags[@]}" evidence/tiff_handler_control.cpp "$builddir/libmotioncorr_core.a" -lfftw3 -lfftw3f -ltiff -lpng -ljpeg -lz -o "evidence/handler-$mode"
  sha256sum "evidence/handler-$mode"
  "evidence/handler-$mode" test-data/synthetic/synthetic_movie.tiff evidence/bad-header.tiff > "evidence/handler-$mode.log" 2>&1
  tail -1 "evidence/handler-$mode.log"
done
python3 - <<'CONTROL'
import hashlib, json, subprocess
from pathlib import Path
src=Path('/home/ubuntu/mc-issue26-envelope/runroot/Movies/20170629_00021_frameImage.tiff')
root=Path.cwd()
results=[]
print('real_input',str(src.resolve()),src.stat().st_size,hashlib.sha256(src.read_bytes()).hexdigest())
for size in [43748634,8388608,41943040]:
    case=root/'evidence'/f'prefix-{size}'
    case.mkdir(exist_ok=True)
    movie=case/'bad.tiff'
    with src.open('rb') as f: movie.write_bytes(f.read(size))
    result={'size':size,'sha256':hashlib.sha256(movie.read_bytes()).hexdigest(),'arms':[]}
    for mode,build in [('modern','build'),('legacy','build-legacy')]:
        cmd=[str(root/build/'motioncorr'),'--i',str(movie),'--o',str(case/mode)+'/', '--use_own','--j','4','--angpix','0.885','--voltage','200','--patch_x','5','--patch_y','5','--skip_defect']
        run=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
        (case/f'{mode}.log').write_text(run.stdout+run.stderr)
        assert run.returncode>0, (mode,size,run.returncode)
        assert 'bad.tiff' in run.stdout+run.stderr
        assert not list((case/mode).rglob('*.mrc'))
        result['arms'].append({'mode':mode,'command':cmd,'exit':run.returncode,'mrc_outputs':0})
    results.append(result)
Path('evidence/real-prefix-controls.json').write_text(json.dumps(results,indent=2)+'\n')
print('REAL_PREFIX_CONTROLS_PASS',len(results)*2)
CONTROL
printf 'COMPAT_AND_PREFIX_RESULT=PASS\n'
date -Is
