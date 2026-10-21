#!/usr/bin/env python3
"""Verify compact evidence integrity and recompute trajectory/field/statistics.
Bulk-image scalar metrics are hash-bound to scratch; this is not a pixel replay.
"""
import hashlib,json,math,os,pathlib,statistics,sys,tarfile
os.environ['OPENBLAS_NUM_THREADS']='1'
import numpy as np
import analyze as calc
s=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else pathlib.Path(__file__).resolve().parents[1]);r=s/'results';raw=s/'raw'
rows=json.load(open(r/'rows.json'));summary=json.load(open(r/'summary.json'));ledger=json.load(open(r/'run-ledger.json'));controls=json.load(open(r/'controls.json'));patches=json.load(open(raw/'ccf-summary.json'))
assert len(rows)==60 and len(ledger)==600 and summary['complete_configs']==60
expected={(f'{fam}-{i:02d}',g) for fam in ['e10216','e12963','e10474f3'] for i in range(10) for g in [5,3]};assert {(x['movie'],x['grid']) for x in rows}==expected
arms=['Rprime','C_none','C_global','C_local','C_both','G_none','G_global','G_local','G_both'];assert all(sorted(x['arms'])==sorted(arms) for x in rows)
pin='afba50a4cebf5238ec2d267ff3ec07d272b13395';v4=json.load(open(raw/'source-validation.json'));vcpu=json.load(open(raw/'cpu64-source-validation.json'))
assert not v4['source_mismatches'] and not vcpu['source_mismatches'] and v4['source_files_checked']==vcpu['source_files_checked']==267
for x in ledger:
 assert x['rc']==0 and x['source_sha']==pin
 mask=x['cpu_mask'];cpus=[]
 for part in mask.split(','):
  if '-' in part:lo,hi=map(int,part.split('-'));cpus+=list(range(lo,hi+1))
  else:cpus.append(int(part))
 assert len(set(cpus))==8
 assert x['binary_sha256']==(v4 if x['gpu'] else vcpu)['binary_sha256']
 arm=x['label'].rsplit('-',1)[1];dc={'R':'none','Rprime':'both'}.get(arm,arm.split('_')[-1])
 assert x['extra_env']['MC_DIAG_CCF_DC']==dc
 assert x['extra_env'].get('MC_DIAG_CCF_DOUBLE')==('1' if arm in ['R','Rprime'] else None)
 grid=x['label'].rsplit('-',2)[1][1:]
 assert x['argv'][x['argv'].index('--patch_x')+1]==x['argv'][x['argv'].index('--patch_y')+1]==grid
 assert x['argv'][x['argv'].index('--j')+1]=='8'
 assert x['gpu']==arm.startswith('G')
 if x['gpu']:
  assert x['gpu_witness_uuids']==[x['cuda_visible_devices']]
  assert x['cuda_visible_devices'] in ['GPU-eddb42fe-4f9a-adde-76d3-b924e14add54','GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d']
 else:assert x['gpu_witness_uuids']==[] and x['cuda_visible_devices']==''
for key,n in [('toggle_off',12),('capture_enabled_off',12),('capture_neutrality',4),('global_selectivity',240)]:
 assert len(controls[key])==n,(key,len(controls[key]))
 assert all(x.get('pass',x.get('bit_equal')) for x in controls[key]),key
assert len(controls['cross_host'])==18 and all(x['pass'] for x in controls['cross_host'])
assert len(controls['legacy_cuda_identity'])==60 and all(x['pass'] for x in controls['legacy_cuda_identity'])
assert len(controls['legacy_cpu_identity'])==60 and all(x['pass'] for x in controls['legacy_cpu_identity'])
parent=json.load(open(raw/'parent-source-validation.json'));assert parent['source_sha']=='31309df0e61277f77b6a9c5210beaca67a582249' and parent['source_files_checked']==266 and not parent['source_mismatches'] and parent['uninstrumented']
package=json.load(open(raw/'package.json'));archive=raw/'native-records.tar.gz';assert hashlib.sha256(archive.read_bytes()).hexdigest()==package['native_archive_sha256']
manifest=json.load(open(raw/'native-records-manifest.json'))
with tarfile.open(archive) as tf:
 data={x.name:tf.extractfile(x).read() for x in tf.getmembers() if x.isfile()}
assert data.keys()==manifest.keys()
for control in controls['toggle_off']:
 p='runs/'+pathlib.Path(control['a']).name+'/run.json';c=json.loads(data[p]);assert c['source_sha']==parent['source_sha'] and c['binary_sha256']==parent['binary_sha256']
 off=json.loads(data['runs/'+pathlib.Path(control['b']).name+'/run.json']);assert off['extra_env']=={}
for name,b in data.items():assert len(b)==manifest[name]['bytes'] and hashlib.sha256(b).hexdigest()==manifest[name]['sha256'],name
bylabel={x['label']:x for x in ledger};assert len(bylabel)==600
def prefix(label):return ('runs/' if bylabel[label]['gpu'] else 'cpu64/runs/')+label
def model(label):
 lines=data[prefix(label)+'/model.txt'].decode().splitlines();g=lines[0].split();n=int(g[3]);scale=float(g[4]);active=int(lines[1].split()[1]);c=np.array([[float(v) for v in l.split()[1:]] for l in lines[2:]]) if active else np.zeros((18,2));return n,c*scale,scale
def global_(label,scale):return np.array([[float(v) for v in l.split()[1:]] for l in data[prefix(label)+'/global.txt'].decode().splitlines()])*scale
def near(a,b):return abs(a-b)<=max(1e-12,1e-11*max(abs(a),abs(b)))
for row in rows:
 base=f"{row['movie']}-p{row['grid']}";rl=base+'-R';n,rc,rs=model(rl);rg=global_(rl,rs)
 for arm,q in row['arms'].items():
  label=base+'-'+arm;n2,c,scale=model(label);assert n2==n
  gl=calc.norms(global_(label,scale)-rg);fl=calc.norms(calc.field(c-rc,n))
  for k in ['max','rms']:
   assert near(gl[k],q['global_px'][k]),(label,'global',k)
   assert near(fl[k],q['local_field_native_px'][k]),(label,'field',k)
  keep=lambda p:sorted(tuple(map(int,k.split(','))) for k,v in patches[p].items() if k!='0,0' and v['converged'])
  assert (keep(prefix(rl))==keep(prefix(label)))==q['accepted_set_equal']
  assert q['accepted_reference']==[list(x) for x in keep(prefix(rl))]
  assert q['accepted_arm']==[list(x) for x in keep(prefix(label))]
for arm in arms:
 vals=[x['arms'][arm]['product']['relative_rmse'] for x in rows];count=sum(v>=.1 for v in vals)
 assert count==summary['arms'][arm]['all']['positive_configs']
 assert summary['arms'][arm]['all']['positive_movies']==len({x['movie'] for x,v in zip(rows,vals) if v>=.1})
 assert near(statistics.median(vals),summary['arms'][arm]['all']['product_relRMSE']['median'])
for name,t in summary['transitions'].items():
 a,b=name.split('->');fa=[x['arms'][a]['product']['relative_rmse']>=.1 for x in rows];fb=[x['arms'][b]['product']['relative_rmse']>=.1 for x in rows]
 for key,va,vb in [('configs',fa,fb),('movies_any_grid',[any(v for x,v in zip(rows,fa) if x['movie']==m) for m in sorted({x['movie'] for x in rows})],[any(v for x,v in zip(rows,fb) if x['movie']==m) for m in sorted({x['movie'] for x in rows})])]:
  c=[sum(x and y for x,y in zip(va,vb)),sum(x and not y for x,y in zip(va,vb)),sum(not x and y for x,y in zip(va,vb)),sum(not x and not y for x,y in zip(va,vb))];n=c[1]+c[2];k=min(c[1:3]);p=min(1.,2*sum(math.comb(n,i) for i in range(k+1))/2**n) if n else 1.
  assert c==t[key]['cells_both_Aonly_Bonly_neither'] and p==t[key]['exact_p_two_sided']
for name,t in summary['backend_transitions'].items():
 a,b=name.split('->');br=summary['backend_continuity'];fa=[q['arms'][a]['relative_rmse']>=.1 for q in br];fb=[q['arms'][b]['relative_rmse']>=.1 for q in br]
 c=[sum(x and y for x,y in zip(fa,fb)),sum(x and not y for x,y in zip(fa,fb)),sum(not x and y for x,y in zip(fa,fb)),sum(not x and not y for x,y in zip(fa,fb))];n=c[1]+c[2];k=min(c[1:3]);p=min(1.,2*sum(math.comb(n,i) for i in range(k+1))/2**n) if n else 1.
 assert c==t['configs']['cells_both_Aonly_Bonly_neither'] and p==t['configs']['exact_p_two_sided']
stage=json.load(open(r/'stage.json'))
for row in stage['rows']:
 if row['case'].startswith('parabola') and row['arm']=='double-zero':
  assert math.dist(row['measured']['candidate'],row['analytic_truth']['vertex'])<1e-8
  assert max(abs(a-b) for a,b in zip(row['measured']['curvature'],row['analytic_truth']['curvature']))<1e-8
native=json.load(open(r/'native-stage.json'));assert len(native['rows'])==706
assert all(x['integer_match'] and x['logged_samples_match_dump'] for x in native['rows'])
assert max(x['fixed_input_double_DC_candidate_difference_px'] for x in native['rows'])<1e-9
transferred=json.load(open(r/'input-transfer-verification.json'));inputs=json.load(open(r/'input-manifest.json'));assert len(transferred)==len(inputs)==30
for a in inputs:
 b=next(x for x in transferred if x['movie']==a['movie']);assert b['movie_sha256']==a['movie_file']['sha256'] and b['input_star_sha256']==a['input_star']['sha256']
 if 'gain' in a:assert b['gain_sha256']==a['gain']['sha256']
report={'status':'PASS','configs':60,'primary_runs':600,'trajectory_field_pairs_recomputed':540,'native_archive_files_verified':len(data),'default_off_controls':12,'capture_enabled_controls':12,'global_selectivity_pairs':240,'fixed_input_native_double_records':706,'limits':'Uses retained native captures and stored image metrics. Does not rerun native binaries or recompute pixels from bulk MRCs; hashes bind those files in scratch. Not motion-truth or scientific qualification.'}
json.dump(report,open(raw/'verification.json','w'),indent=1);print(json.dumps(report))
