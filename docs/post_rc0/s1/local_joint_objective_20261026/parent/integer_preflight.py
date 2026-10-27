from pathlib import Path
import hashlib,json
import numpy as np

OUT=Path(__file__).parent
ROOT=Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1/native-map-bundle-r1')
idx_file=ROOT/'INDEX.json'
assert hashlib.sha256(idx_file.read_bytes()).hexdigest()=='5b3dde3aefa3ff647927cbf702b3489fc1a470083fbcc23644bb8eb2f191c8d3'
index={e['path']:e for e in json.loads(idx_file.read_text())['files']}

def load(p,name):
    meta=json.loads((p/(name+'.json')).read_text())
    f=p/(name+'.bin'); data=f.read_bytes(); ent=index[str(f.relative_to(ROOT))]
    assert len(data)==ent['bytes'] and hashlib.sha256(data).hexdigest()==ent['sha256']
    a=np.frombuffer(data,dtype=meta['dtype']).reshape(meta['shape'])
    assert np.isfinite(a).all()
    return a

def complex_array(p,name):
    a=load(p,name).astype(np.float64)
    return a[...,0]+1j*a[...,1]

mult=np.full(22,2.);mult[[0,21]]=1
lags=np.arange(-15,16)
kx=np.arange(22);ky=np.arange(32);ky[ky>16]-=32
EX=np.exp(2j*np.pi*np.outer(lags,kx)/42)
EY=np.exp(2j*np.pi*np.outer(lags,ky)/32)
bound=5e-6
states=[]
for cy in [79,47]:
    p=ROOT/'evidence/runs/ON/capture'/('patch-62-%d'%cy)
    for it in [1,2]:
        for f in range(5):
            tag='iter%d-frame%d'%(it,f)
            s=complex_array(p,tag+'-weighted-api-consumed')
            assert s[0,0]==0
            l1=float(np.sum(mult[None,:]*np.abs(s)))
            states.append((cy,it,f,p,tag,s,l1))
l1_record=[{'patch_y':cy,'iteration':it,'frame':f,'L1_consumed':l1} for cy,it,f,p,tag,s,l1 in states]
estimate=float(.5*sum(np.finfo(np.float32).eps*np.log2(1344)*l1 for cy,it,f,p,tag,s,l1 in states)/4)
(OUT/'INTEGER_PREFLIGHT_L1_BEFORE.json').write_text(json.dumps({'rows':l1_record,'mean_state_half_sum_heuristic':estimate,
    'fixed_bound':bound,'bound_less_than_twice_heuristic':bound<2*estimate},indent=2)+'\n')
rows=[]
for cy,it,f,p,tag,s,l1 in states:
    actual=load(p,tag+'-real-map').astype(np.float64)[np.ix_(lags%32,lags%42)]
    predicted=np.real(EY@(s*mult[None,:])@EX.T)
    pre=complex_array(p,tag+'-weighted-pre-dc')
    wrong_dc=np.real(EY@(pre*mult[None,:])@EX.T)
    wrong_m=mult.copy();wrong_m[0]=2
    doubled=np.real(EY@(s*wrong_m[None,:])@EX.T)
    err=float(np.max(np.abs(predicted-actual)))
    rows.append({'patch_y':cy,'iteration':it,'frame':f,'L1_consumed':l1,'max_error':err,'pass':err<=bound,
        'sign_mutant_max_error':float(np.max(np.abs(predicted[::-1,::-1]-actual))),
        'axis_mutant_max_error':float(np.max(np.abs(predicted.T-actual))),
        'omit_dc_mutant_max_error':float(np.max(np.abs(wrong_dc-actual))),
        'double_x0_mutant_max_error':float(np.max(np.abs(doubled-actual)))})
mutants={a:any(r[a+'_mutant_max_error']>bound for r in rows) for a in ['sign','axis','omit_dc','double_x0']}
result={'bound':bound,'n_maps':len(rows),'n_lags_per_map':len(lags)**2,'rows':rows,'mutants_rejected':mutants,
        'ky16_sign_and_Hermitian_mutants':'NOT_OBSERVABLE at this weight; not PASS',
        'pass':all(r['pass'] for r in rows) and mutants['sign'] and mutants['axis']}
(OUT/'INTEGER_PREFLIGHT_RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({'pass':result['pass'],'n_maps':len(rows),'max_error':max(r['max_error'] for r in rows),'mutants':mutants}))
assert result['pass']
