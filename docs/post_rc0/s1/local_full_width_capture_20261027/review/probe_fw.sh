#!/bin/bash
set -u
O=/tmp/mc-fullwidth-ccf-capture-opus-review-20261027-r1/fwdump; W=/tmp/mc-capext-20261027-r2; cd $O
FL="-O3 -DNDEBUG -std=gnu++17 -arch arm64 -Xpreprocessor -fopenmp -DMC_EXPERIMENT_CCF_DC -I/opt/homebrew/opt/libomp/include -isystem /opt/homebrew/Cellar/fftw/3.3.11/include -isystem /opt/homebrew/include"
LIBS="$W/build/libmotioncorr_core.a /opt/homebrew/Cellar/fftw/3.3.11/lib/libfftw3.dylib /opt/homebrew/Cellar/fftw/3.3.11/lib/libfftw3f.dylib /opt/homebrew/opt/libomp/lib/libomp.dylib /opt/homebrew/lib/libtiff.dylib /opt/homebrew/lib/libpng.dylib /opt/homebrew/lib/libjpeg.dylib -lz"
c++ $FL -I$W/src dump_fw.cpp -o dump_fw $LIBS 2>build.log; echo build_rc=$?
rm -rf out; OMP_NUM_THREADS=2 ./dump_fw $O/out; echo run_rc=$?
/Users/alex.konstantinov/.local/bin/python3 -I - $O/out <<'PY'
import json,sys,pathlib
r=pathlib.Path(sys.argv[1]);js=sorted(r.rglob('*.json'));bad=[]
for p in js:
    try: json.loads(p.read_text())
    except Exception as e: bad.append((str(p.relative_to(r)),str(e)))
print('json_files',len(js),'invalid',len(bad),bad[:3])
s=json.loads((r/'session.json').read_text());print('session',s['schema'],s['selected_centres'],s['capture_mode'])
for d in ['patch-104-15','patch-62-79']:
    pj=json.loads((r/d/'patch.json').read_text());fc=json.loads((r/d/'fft-config.json').read_text())
    print(d,pj['centre'],pj['extents_xy_halfopen'],pj['capture_mode'],pj['local_full_width_weight'],fc['weight_x_norm'],fc['weight_nfx_inherited_not_used'])
print('dirs',sorted(x.name for x in r.iterdir()))
PY
echo files=$(find $O/out -type f | wc -l) size=$(du -sk $O/out | cut -f1)KiB
rm -f dump_fw; rm -rf out
