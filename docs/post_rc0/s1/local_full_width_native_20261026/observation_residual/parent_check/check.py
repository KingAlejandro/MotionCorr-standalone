import os, json, hashlib, shutil
from pathlib import Path
import numpy as np

src = Path('/tmp/mc-lfw-observation-residual-20261027-r1')
out = Path(__file__).resolve().parent
assert shutil.disk_usage(out).free > 100_000_000
assert all(os.environ[k] == '1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS'))
pins = json.loads((src/'PINS.json').read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
for p in pins['inputs'].values():
    assert sha(p['path']) == p['sha256'], p['path']
data = json.loads((src/'out/observation_residual.json').read_text())
fits = json.loads(Path(pins['inputs']['screen_out/stage1_fit.json']['path']).read_text())['native']
results = {}
def rms(v): return float(np.sqrt(np.mean(np.sum(v*v, axis=-1))))
for case in ('noisy','affine','pedestal'):
    truth = np.load(pins['inputs'][f'truth/{case}_field.npy']['path'])
    for arm in ('OFF','ON'):
        key = f'{case}/{arm}'
        rt = json.loads(Path(pins['inputs'][f'run/{case}/{arm}/runtime.json']['path']).read_text())
        text = Path(pins['inputs'][f'run/{case}/{arm}/{case}.star']['path']).read_text()
        block = text.split('data_local_shift',1)[1]
        groups = {}
        for line in block.splitlines():
            cols = line.split()
            if len(cols) != 5 or cols[0].startswith(('_','#')): continue
            f,x,y,sx,sy = map(float,cols)
            p = (int(x),int(y))
            groups.setdefault(p,{})[int(f)-1] = (sx,sy)
        patches = sorted(groups)
        assert all(set(groups[p]) == set(range(5)) for p in patches)
        y = np.array([[groups[p][g] for g in range(5)] for p in patches])
        G = np.asarray(rt['global'])
        H = np.array([[truth[g,p[1],p[0]]-G[g] for g in range(5)] for p in patches])
        assert np.all(H[:,0] == 0)
        trH = H + H[:,1:2]/2
        e = y-trH
        s = y-y[:,0:1]
        eta = s-H
        saved = data['cases'][key]
        lookup = {tuple(p):i for i,p in enumerate(saved['patches'])}
        order = [lookup[p] for p in patches]
        deviations = {}
        for name,value in [('y',y),('H',H),('TrH',trH),('e_tr',e),('s',s),('eta',eta)]:
            deviations[name] = float(np.max(np.abs(value-np.asarray(saved[name])[order])))
            assert deviations[name] < 1e-13
        point_fit = {}
        u = np.array([p[0]/128-.5 for p in patches])
        v = np.array([p[1]/96-.5 for p in patches])
        spatial = np.stack([np.ones_like(u),u,u*u,v,v*v,u*v],axis=1)
        times = np.arange(5.)
        basis = np.stack([times,times**2,times**3],axis=1)
        for name in ('native_runtime_coeff','legacy_coeff','B2_coeff'):
            c = np.asarray(fits[key][name]).reshape(2,6,3)
            field = np.einsum('ps,gtk,as k->pga',spatial,basis[:,None,:],c) if False else np.einsum('ps,gk,ask->pga',spatial,basis,c)
            error = field-H
            dev = float(np.max(np.abs(error-np.asarray(saved['fitted'][name]['err'])[order])))
            assert dev < 1e-13
            point_fit[name] = {'rms_px':rms(error[:,1:]),'max_abs_reproduction_px':dev}
        patch_ms = np.mean(np.sum(eta[:,1:]**2,axis=-1),axis=1)
        worst = int(np.argmax(patch_ms))
        results[key] = {'n_patches':len(patches),'eta_rms_px':rms(eta[:,1:]),'frame_rms_px':[rms(eta[:,g]) for g in range(1,5)],
          'worst_patch':patches[worst],'worst_patch_rms_px':float(np.sqrt(patch_ms[worst])),
          'descriptive_fraction_of_sum_squared_errors':float(patch_ms[worst]/patch_ms.sum()),
          'max_array_reproduction_px':max(deviations.values()),'point_fits':point_fit,
          'closure_max_px':float(np.max(np.abs(eta-(e-e[:,0:1]))))}
(out/'RESULT.json').write_text(json.dumps({'pins_verified':len(pins['inputs']),'results':results,'scope':'Saved metadata and truth only; no imported author code, fit or native run.'},indent=2)+'\n')
print(json.dumps({'pins_verified':len(pins['inputs']),'case_results':results},indent=1))
