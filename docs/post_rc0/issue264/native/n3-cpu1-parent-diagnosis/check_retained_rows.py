# SPDX-License-Identifier: GPL-2.0-or-later
# Independent read-only STAR diagnosis: no import/execution of original grader.
from pathlib import Path
from decimal import Decimal
import json,hashlib,tarfile,subprocess,datetime,platform
ROOT=Path('/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-96f54dde')
D=ROOT/'docs/post_rc0/issue264/native/n3-cpu1-result'
ARCHIVE=D/'raw/evidence.tar'
EXPECTED='3cc13020d35aaf7113fe16878e8eb63c11652863fd73c0da3974fc7fa09f2760'
assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()==EXPECTED
LABELS=['_rlnMicrographFrameNumber','_rlnMicrographShiftX','_rlnMicrographShiftY']
def parse(text):
 lines=text.splitlines();starts=[i for i,l in enumerate(lines) if l.strip()=='data_global_shift']
 if len(starts)!=1:raise ValueError('require one global block')
 labels=[];rows=[];loop=False
 for line in lines[starts[0]+1:]:
  line=line.split('#',1)[0].strip()
  if not line:continue
  if line.startswith('data_'):break
  if line=='loop_':
   if loop:raise ValueError('duplicate loop')
   loop=True;continue
  if line.startswith('_'):
   if rows or len(line.split())!=1:raise ValueError('invalid loop labels')
   labels.append(line);continue
  if not loop or labels!=LABELS:raise ValueError('unexpected schema')
  v=line.split()
  if len(v)!=3 or not v[0].isdigit():raise ValueError('invalid row')
  x,y=Decimal(v[1]),Decimal(v[2])
  if not x.is_finite() or not y.is_finite():raise ValueError('nonfinite row')
  rows.append((int(v[0]),x,y))
 if labels!=LABELS or [v[0] for v in rows]!=list(range(1,13)):raise ValueError('missing/duplicate/reordered frame')
 return rows
def legacy_block(text):return text.split('data_global_shift',1)[1].split('data_',1)[0]
with tarfile.open(ARCHIVE,'r:') as tar:
 files={}
 for m in tar:
  if m.isfile() and m.name.endswith('/out/km_local_nonsquare.star'):
   assert m.name not in files
   files[m.name]=tar.extractfile(m).read()
assert len(files)==24
cases=sorted({n.split('/')[2] for n in files});assert len(cases)==8
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reviewed_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'native_source':'3751bd05a95412dff468557141f2e7e01ad21831','archive_sha256':EXPECTED,'platform':platform.platform(),'evidence_layer':'Read-only retained STAR parsing; no native, original grader, MRC payload or full-precision trace execution. No regrade.','pairs':[],'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}
for case in cases:
 texts={a:files[f'n3-cpu1/ov-{a}-cpu/{case}/out/km_local_nonsquare.star'].decode() for a in ['base','cand','mut']}
 rows={a:parse(t) for a,t in texts.items()}
 assert rows['base']==rows['cand']==rows['mut']
 b,c=legacy_block(texts['base']),legacy_block(texts['cand'])
 # Show that removing only comments and empty lines, not numeric tokens, removes the raw mismatch.
 clean=lambda t:[l.strip() for l in t.splitlines() if l.split('#',1)[0].strip()]
 assert clean(b)==clean(c)
 out['pairs'].append({'case':case,'frame_rows':12,'all_3_arms_exact_printed_numeric_equality':True,'legacy_raw_blocks_equal':b==c,'all_noncomment_nonblank_block_lines_equal':True})
# Actual native STAR controls: value error, missing/duplicate row, nonfinite and trailing model blocks.
ref=files['n3-cpu1/ov-cand-cpu/A_x_legacy_false_accept/out/km_local_nonsquare.star'].decode();base=parse(ref)
lines=ref.splitlines();index=next(i for i,l in enumerate(lines) if l.split()==['2','-1.70013','1.382446'])
def edited(value):
 a=lines.copy();a[index]=value;return '\n'.join(a)+'\n'
controls={}
changed=edited('2 -1.700129 1.382446');controls['1e-6_value_change_detected']=parse(changed)!=base
for name,text in [('missing_row','\n'.join(lines[:index]+lines[index+1:])),('duplicate_row','\n'.join(lines[:index]+[lines[index]]+lines[index:])),('nonfinite',edited('2 NaN 1.382446'))]:
 try:parse(text)
 except ValueError:controls[name+'_rejected']=True
 else:controls[name+'_rejected']=False
real_following=files['n3-cpu1/ov-base-cpu/A_x_legacy_false_accept/out/km_local_nonsquare.star'].decode()
controls['real_writer_following_model_changes_raw_not_rows']=legacy_block(ref)!=legacy_block(real_following) and parse(ref)==parse(real_following)
assert all(controls.values());out['controls']=controls
old=json.loads((D/'raw/RESULTS.json').read_text());bad={x['case'] for x in old['base_vs_candidate'] if x['status']=='FAIL'}
assert bad=={x['case'] for x in out['pairs'] if not x['legacy_raw_blocks_equal']}
assert len(bad)==5 and all(not x['same_global_shifts'] and not x['same_decision'] and not x['image_data_equal'] for x in old['base_vs_candidate'] if x['status']=='FAIL')
out['original_subset']='FAIL retained:3pairsPASS/5pairsFAIL,24CPUrowsPASS,16CUDArowsUNRUN; no new subset verdict'
out['diagnostic_conclusion']='Five pair failures coincide exactly with comment/blank formatting in raw global-block comparison. All24 retained printed trajectories equal across arms; full-precision/machine-state equality is not established.'
Path(__file__).with_name('CHECK.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'pairs':len(cases),'STARs':len(files),'printed_rows_per_STAR':12,'legacy_raw_mismatches':len(bad),'controls':controls,'original_subset':'FAIL unchanged'}))
