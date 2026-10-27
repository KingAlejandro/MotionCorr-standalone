"""Parent's independent scoring; run only after stage-1 outputs are sealed.

Usage: score.py CANDIDATES_JSON OUT_JSON
CANDIDATES_JSON is an adapter-written list: patch_y, label, shifts (5x2), selected.
No optimization, registration, refitting or pixel reads occur here.
"""
from pathlib import Path
import hashlib, json, sys
import numpy as np

ROOT = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1')
CAP = ROOT/'native-map-bundle-r1/evidence/runs/ON/capture'
TRUTH = ROOT/'capture-bundle-r1/truth-scoring-only/noisy_field.npy'

def array(p, name):
    m = json.loads((p/(name+'.json')).read_text())
    a = np.fromfile(p/(name+'.bin'), dtype=m['dtype']).reshape(m['shape'])
    assert a.nbytes == m['bytes'] and np.isfinite(a).all()
    return a

def objective(p, shifts):
    # A separately coded raw-half-plane phase objective, not real-map interpolation.
    ff = []
    for f in range(5):
        a = array(p, 'initial-frame%d-fft'%f).astype(np.float64)
        ff.append(a[...,0]+1j*a[...,1])
    weight = np.exp(-2*150*((np.arange(22)[None,:]/42.)**2 + (np.where(np.arange(32)>16,np.arange(32)-32,np.arange(32))[:,None]/32.)**2)).astype(np.float32).astype(np.float64)
    kx = np.arange(22,dtype=float)[None,:]
    ky = np.arange(32,dtype=float)[:,None]
    ky[ky>16] -= 32
    mult = np.full((1,22),2.0); mult[0,[0,21]]=1
    total = 0.0
    for j in range(5):
        for f in range(j+1,5):
            a = ff[j]*ff[f].conj()*weight
            a[0,0]=0
            d = shifts[f]-shifts[j]
            phase = 2*np.pi*(kx*d[0]/42+ky*d[1]/32)
            total += float(np.real(np.sum(mult*a*np.exp(1j*phase))))
    return total

def metrics(e):
    n = np.linalg.norm(e,axis=-1)
    return {'rms':float(np.sqrt(np.mean(n*n))), 'p95':float(np.percentile(n,95)), 'max':float(n.max())}

def main():
    inp, out = map(Path,sys.argv[1:3])
    candidates = json.loads(inp.read_text())
    assert hashlib.sha256(TRUTH.read_bytes()).hexdigest() == '839c484f08ced435120a3f7c60267b95959bc5c06993f7c3015d61ffa3b95799'
    truth = np.load(TRUTH,allow_pickle=False)
    assert truth.shape == (5,96,128,2) and np.isfinite(truth).all()
    rows=[]; truths={}
    for cy in [79,47]:
        p = CAP/('patch-62-%d'%cy)
        desired = truth[:,cy,62,:]-array(p,'global-shifts')
        assert not desired[0].any()
        truths[cy]={'local_truth_px':desired.tolist(),'raw_phase_J':objective(p,desired)}
    for row in candidates:
        cy = row['patch_y']; assert cy in [79,47]
        s = np.asarray(row['shifts'],dtype=float)
        assert s.shape == (5,2) and np.isfinite(s).all() and not s[0].any()
        desired = np.asarray(truths[cy]['local_truth_px'])
        error = s-desired
        torus = (error+np.array([21.,16.]))%np.array([42.,32.])-np.array([21.,16.])
        p = CAP/('patch-62-%d'%cy)
        rows.append({**row,'physical_frequency_J_parent':objective(p,s),'physical_error_vectors_px':error.tolist(),
                     'physical_error_px':metrics(error),'physical_error_A':metrics(.885*error),
                     'periodic_error_px_report_only':metrics(torus)})
    res={'schema':'local-physical-frequency-parent-score/1','numpy':np.__version__,
         'input_sha256':hashlib.sha256(inp.read_bytes()).hexdigest(),'rows':rows,'truth_points':truths,
         'scientific_acceptance':'NOT_TESTED: point-center trajectories do not replace full fixed-ROI field gates',
         'global_optimality':'UNPROVEN_GLOBAL'}
    out.write_text(json.dumps(res,indent=2,allow_nan=False)+'\n')
    print('scored',len(rows),'saved candidate trajectories')

if __name__=='__main__':main()
