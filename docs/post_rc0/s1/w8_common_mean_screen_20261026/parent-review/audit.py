"""Independent saved-data audit. No fitter, native producer, or image payload reads."""
from pathlib import Path
import hashlib, importlib.util, json, sys
import numpy as np

P = Path('/tmp/mc-w8-common-mean-screen-20261026')
OUT = Path(__file__).parent
checked = 0
for line in (P/'SHA256SUMS').read_text().splitlines():
    digest, rel = line.split(None, 1)
    q = P/rel.strip()
    assert hashlib.sha256(q.read_bytes()).hexdigest() == digest, rel
    checked += 1
rf = json.loads(next(P.glob('authority_w8_*/**/refit.json')).read_text())['movies']
s1 = json.loads((P/'results/stage1_d.json').read_text())['movies']
sc = json.loads((P/'results/stage2_score.json').read_text())
rows = {m['movie']: m for m in sc['movies']}
limits = {'rms': .20, 'p95': .40, 'max': .80}
passed = lambda m: all(np.isfinite(m[k]) and m[k] <= limits[k] for k in limits)
inmodel = [m for m in rows.values() if m.get('set') == 'inmodel']
assert len(rows) == 90 and len(inmodel) == 80
assert len(rf) == 100 and sum(m['status']=='NO_LOCAL_RETAINED' for m in rf.values()) == 10
new_fail = sorted(m['movie'] for m in inmodel if passed(m['B2']) and not passed(m['CM']))
rescued = sorted(m['movie'] for m in inmodel if not passed(m['B2']) and passed(m['CM']))
assert len(new_fail) == 5 and len(rescued) == 4
fail12 = [m for m in inmodel if not passed(m['B2'])]
assert len(fail12) == 12
groups = {s: np.mean([m['CM']['rms']**2-m['B2']['rms']**2 for m in fail12 if m['seed']==s])
          for s in sorted({m['seed'] for m in fail12})}
median = float(np.median(list(groups.values())))
assert abs(median-sc['summary']['rule1_median_of_8_seed_group_mean_dMS_A2']) < 1e-14
counts = {a: sum(passed(m[a]) for m in inmodel) for a in ['native','B2','CM']}
assert counts == {'native':22, 'B2':68, 'CM':67}
sys.path.insert(0, str(P/'src_4fa272f6/test-data'))
import generate_realistic_motion as gen

def local(coeff, coords, nx, ny):
    u,v = coords[:,0]/nx-.5, coords[:,1]/ny-.5
    basis = [np.ones_like(u),u,u*u,v,v*v,u*v]
    result = np.zeros((40,len(u),2))
    # Explicit sums independently implement coefficient and physical-time order.
    for f in range(40):
        for axis in range(2):
            for spatial in range(6):
                for k in range(1,4):
                    result[f,:,axis] += coeff[axis,3*spatial+k-1]*basis[spatial]*f**k
    return result

results = []
for name in new_fail + rescued:
    rfit = rf[name]
    centers = np.asarray(rfit['patch_centres'])
    star = P/'inputs/runs'/name/'F/output/movie.star'
    block = None; observed = {}
    for line in star.read_text().splitlines():
        a = line.split()
        if not a: continue
        if a[0].startswith('data_'): block = a[0]
        elif block == 'data_local_shift' and len(a)==5 and not a[0].startswith('_'):
            f,x,y,dx,dy = map(float,a)
            key = (int(f)-1,x,y)
            assert key not in observed
            observed[key] = [dx,dy]
    obs = np.asarray([[observed[(f,float(x),float(y))] for x,y in centers] for f in range(40)])
    assert len(observed)==1000 and np.isfinite(obs).all()
    coeff = np.asarray([rfit['coeff_x'],rfit['coeff_y']])
    lm = local(coeff,centers,rfit['nx'],rfit['ny']).mean(1)
    mean = obs.mean(1)
    d = mean-mean[0]-lm
    assert not d[0].any() and np.isfinite(d).all()
    delta = float(np.max(np.abs(d-np.asarray(s1[name]['d']))))
    assert delta < 1e-10
    cond,seed = name.rsplit('-s',1)
    recipe = gen.recipe(cond,int(seed))
    x,y = np.meshgrid(np.linspace(32,recipe['nx']-33,129),np.linspace(32,recipe['ny']-33,129))
    coords = np.column_stack((x.ravel(),y.ravel()))
    truth = -np.stack([gen.displacement(recipe,f,coords[:,0],coords[:,1]) for f in range(40)])
    old = local(coeff,coords,recipe['nx'],recipe['ny'])+np.asarray(rfit['global_runtime'])[:,None,:]
    actual = {}
    for arm,field in [('B2',old),('CM',old+d[:,None,:])]:
        norm = np.linalg.norm((field-truth)*recipe['pixel_size'],axis=-1)
        met = {'rms':float(np.sqrt(np.mean(norm**2))), 'p95':float(np.percentile(norm,95)), 'max':float(norm.max())}
        err = max(abs(met[k]-rows[name][arm][k]) for k in limits)
        assert err < 1e-10,(name,arm,err)
        actual[arm] = met
    results.append({'movie':name,'d_max_difference_px':delta,**actual})
result = {'status':'CLEAR for bounded NO-GO reporting','numpy':np.__version__,'manifest_files_verified':checked,
          'new_fail':new_fail,'rescued':rescued,'passes':counts,'seed_group_median_dMS_A2':median,
          'independently_recomputed_nine_movies':results,'no_native_or_fitter_run':True}
(OUT/'RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='independently_recomputed_nine_movies'}))
