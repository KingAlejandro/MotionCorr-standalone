# SPDX-License-Identifier: GPL-2.0-or-later
import argparse,hashlib,json,pathlib,subprocess,sys
ap=argparse.ArgumentParser(description='Compile the production guard helper, exact legacy block, and two deliberate mutants against one unchanged oracle.')
ap.add_argument('--out',type=pathlib.Path,required=True);ap.add_argument('--compiler',default='c++')
args=ap.parse_args();R=pathlib.Path(__file__).resolve().parents[3];O=args.out.resolve();O.mkdir(parents=True,exist_ok=False)
base='3691374061f782bc84531fd1c79d017ddcb5a7c2';old=subprocess.check_output(['git','show',base+':src/motioncorr_runner.cpp'],cwd=R,text=True)
a=old.index('\t\t// Validation of the model:');b=old.index('\n\t\tif (largest_delta > MAXIMUM_TOLERANCE)',a);fragment=old[a:b]
legacy='''#include <cmath>
namespace motioncorr {
template<class Real,class Model> Real maximumNeighbourShiftDelta(const Model &m,int nx,int ny,int n_frames,Real stop_above) {
using RFLOAT=Real; const Model *model=&m; (void)stop_above;
'''+fragment+'\nreturn largest_delta;\n}}\n'
header=(R/'src/local_motion_guard.h').read_text()
cases={'legacy_exact_runner_block':legacy,'fixed':header,
       'mutant_uncentred':header.replace(' - Real(0.5)',''),
       'mutant_invalid_last_pair':header.replace('nx - 1 - (axis == 0)','nx - 1').replace('ny - 1 - (axis == 1)','ny - 1')}
results=[]
for label,h in cases.items():
 d=O/label;(d/'src').mkdir(parents=True,exist_ok=False);(d/'src/local_motion_guard.h').write_text(h)
 cmd=[args.compiler,'-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(d),'-I',str(R),str(R/'tests/test_local_motion_distortion_guard.cpp'),'-o',str(d/'test')]
 c=subprocess.run(cmd,text=True,capture_output=True);(d/'compile.stdout').write_text(c.stdout);(d/'compile.stderr').write_text(c.stderr);assert c.returncode==0,(label,c.stderr)
 r=subprocess.run([str(d/'test')],text=True,capture_output=True);(d/'run.stdout').write_text(r.stdout);(d/'run.stderr').write_text(r.stderr)
 assert r.returncode==(0 if label=='fixed' else 1),(label,r.returncode,r.stdout,r.stderr)
 results.append({'case':label,'compile_argv':cmd,'compile_exit':c.returncode,'test_exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'header_sha256':hashlib.sha256(h.encode()).hexdigest(),'binary_sha256':hashlib.sha256((d/'test').read_bytes()).hexdigest()})
d={'kind':'host C++ helper regression; no MotionCorr movie/CUDA execution','base':base,'legacy_runner_sha256':hashlib.sha256(old.encode()).hexdigest(),'legacy_block_sha256':hashlib.sha256(fragment.encode()).hexdigest(),'fixed_test_sha256':hashlib.sha256((R/'tests/test_local_motion_distortion_guard.cpp').read_bytes()).hexdigest(),'compiler':subprocess.check_output([args.compiler,'--version'],text=True),'rows':results,'limitations':['Standalone production guard helper exercised with independent finite-grid polynomial oracle.','End-to-end CPU/CUDA/native fitting/publication not executed; current source review and CI pending.','No guard threshold or gate relaxed; mutations and exact legacy block must exit1 ordinarily.']}
(O/'host_results.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps([{k:r[k] for k in ['case','compile_exit','test_exit','stdout']} for r in results],indent=2))
