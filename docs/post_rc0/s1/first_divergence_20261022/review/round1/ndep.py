# N-dependence probe of the linearised instability (reviewer-only, synthetic phase-ramp frames
# from the hash-bound integer target; not a fixture, not a production claim).
import sys, numpy as np, importlib.util
spec = importlib.util.spec_from_file_location('ind', sys.argv[2]); 
src = open(sys.argv[2]).read().split('out = {}')[0]   # reuse function defs only
ns = {'__name__':'x', 'sys':sys}; sys.argv_backup = sys.argv; exec(src, ns)
tgt = np.load(f'{sys.argv[1]}/fixtures/integer_target.npy').astype(np.float64); Ft = np.fft.fft2(tgt)/(128*96)
for vel in ((-1.0, 2.0), (-0.8125, 0.53125)):
    for N in (5, 9, 13, 20):
        truth = np.array([[vel[0]*f, vel[1]*f] for f in range(N)])
        F0 = np.stack([ns['shiftF'](Ft, -t) for t in truth]); ns['NF'] = N
        row = []
        for W, name in ((ns['W_prod'], 'prod'), (ns['W_iso'], 'iso')):
            for it, tol in ((5, 0.5), (50, 1e-9)):
                acc, conv, hist = ns['replay'](F0, W, iters=it, tol=tol)
                row.append(f"{name}/{it}it rms={ns['rms'](acc, truth):.3f} conv={conv}")
        g = N/(N-1); print(vel, N, f"lin eig prod={1-g*1.7564:.3f} iso={1-g*1.2153:.3f}", ' | '.join(row), flush=True)
