# Independent reviewer reproduction (different calculation path from the W4 packet):
# frames read from the stored .mrcs, full complex fft2, full-grid weight, upsampled-grid
# continuous maximum (no BFGS), own replay, and a linearised stability analysis.
import sys, json, hashlib, numpy as np
RAW = sys.argv[1]
NX, NY, NF, B, S = 128, 96, 5, 150.0, 47
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()
def mrcs(p):
    b = open(p,'rb').read(); h = np.frombuffer(b[:1024], np.int32)
    nx, ny, nz, mode, next_ = h[0], h[1], h[2], h[3], h[23]
    assert mode == 2
    return np.frombuffer(b[1024+next_:], np.float32).reshape(nz, ny, nx).astype(np.float64)
kx = np.fft.fftfreq(NX)*NX; ky = np.fft.fftfreq(NY)*NY
W_prod = np.exp(-2*B*((ky[:,None]/NY)**2 + (np.abs(kx)[None,:]/(NX//2+1))**2))
W_iso  = np.exp(-2*B*((ky[:,None]/NY)**2 + (kx[None,:]/NX)**2))
def cmap(R_, F, W): return np.real(np.fft.ifft2(R_*np.conj(F)*W))
def winner(m):
    sub = np.roll(np.roll(m, S, 0), S, 1)[:2*S+1, :2*S+1]   # rows y=-S..S, cols x=-S..S
    i = int(np.argmax(sub))                                  # first max in row-major = CPU strict '>' order
    y, x = divmod(i, 2*S+1); return x-S, y-S
def parab(m):
    px, py = winner(m); c = m[py%NY, px%NX]
    out=[]
    for vp, vn, p in ((m[py%NY,(px+1)%NX], m[py%NY,(px-1)%NX], px), (m[(py+1)%NY,px%NX], m[(py-1)%NY,px%NX], py)):
        d = vp+vn-2*c; out.append(p-0.5*(vp-vn)/d if abs(d)>1e-15 else float(p))
    return np.array(out)
def fine_max(Sfull, start, up=64, half=1.5):
    # direct band-limited evaluation on a fine grid around the winner, then 2-level zoom
    cx, cy = start
    for lev in range(3):
        xs = cx + np.linspace(-half, half, up+1); ys = cy + np.linspace(-half, half, up+1)
        ex = np.exp(2j*np.pi*np.outer(kx/NX, xs)); ey = np.exp(2j*np.pi*np.outer(ys, ky/NY))
        v = np.real(ey @ Sfull @ ex)     # v[iy, ix]
        iy, ix = np.unravel_index(np.argmax(v), v.shape); cx, cy = xs[ix], ys[iy]; half = half/up*4
    return np.array([cx, cy])
def hess(Sfull, p):
    ph = Sfull*np.exp(2j*np.pi*((kx/NX)[None,:]*p[0] + (ky/NY)[:,None]*p[1]))
    KX = (kx/NX)[None,:]; KY = (ky/NY)[:,None]; g = -(2*np.pi)**2
    return np.array([[np.real((g*KX*KX*ph).sum()), np.real((g*KX*KY*ph).sum())],
                     [np.real((g*KX*KY*ph).sum()), np.real((g*KY*KY*ph).sum())]])
def shiftF(F, c): return F*np.exp(-2j*np.pi*((kx/NX)[None,:]*c[0] + (ky/NY)[:,None]*c[1]))
def replay(F0, W, fixed=False, iters=5, tol=0.5, est='parabola'):
    F = F0.copy(); acc = np.zeros((NF,2)); conv=False; hist=[]
    for it in range(iters):
        cand = np.zeros((NF,2))
        for f in range(NF):
            R_ = F[0] if fixed else F.sum(0)-F[f]
            m = cmap(R_, F[f], W)
            cand[f] = parab(m) if est=='parabola' else fine_max(R_*np.conj(F[f])*W, winner(m))
        cand -= cand[0]; acc += cand
        for f in range(1,NF): F[f] = shiftF(F[f], cand[f])
        rmsd = np.sqrt((cand**2).sum()/NF); hist.append(float(rmsd))
        if rmsd < tol: conv=True; break
    return acc, conv, hist
def rms(a, t): return float(np.sqrt(np.mean(np.sum((a-t)**2,1))))
out = {}
for case in ('integer','fractional'):
    fr = mrcs(f'{RAW}/fixtures/{case}.mrcs'); tgt = np.load(f'{RAW}/fixtures/{case}_target.npy').astype(np.float64)
    field = np.load(f'{RAW}/fixtures/{case}_field.npy'); truth = field[:,0,0,:].astype(np.float64)
    o = dict(mrcs_sha=sha(f'{RAW}/fixtures/{case}.mrcs'), field_shape=list(field.shape), truth=truth.tolist(),
             field_constant=float(np.abs(field-field[:,:1,:1,:]).max()),
             frame0_vs_target=float(np.abs(fr[0]-tgt).max()), frame0_vs_target_flipud=float(np.abs(fr[0]-tgt[::-1]).max()))
    F0 = np.fft.fft2(fr)/(NX*NY)
    for name, kw in [('sumothers_parabola_5it', {}), ('sumothers_parabola_50it_tol1e-9', dict(iters=50, tol=1e-9)),
                     ('fixed0_parabola_5it', dict(fixed=True)), ('sumothers_finemax_50it_tol1e-9', dict(iters=50, tol=1e-9, est='fine')),
                     ('sumothers_parabola_5it_isotropicW', dict(W=W_iso))]:
        W = kw.pop('W', W_prod); acc, conv, hist = replay(F0, W, **kw)
        o[name] = dict(rms_px=rms(acc, truth), converged=conv, rmsd_hist=hist[:8]+(['...',hist[-1]] if len(hist)>8 else []), traj=acc.tolist())
    out[case] = o
# Known-shift oracle on the target with production weight: 81 offsets
tgt = np.load(f'{RAW}/fixtures/integer_target.npy').astype(np.float64); Ft = np.fft.fft2(tgt)/(NX*NY)
for wname, W in (('production', W_prod), ('isotropic', W_iso)):
    errs=[]; cont=[]
    for mx in np.arange(-1,1.0001,0.25):
        for my in np.arange(-1,1.0001,0.25):
            mu = np.array([mx,my]); Ff = shiftF(Ft, -mu); Sf = Ft*np.conj(Ff)*W
            m = cmap(Ft, Ff, W); p = parab(m); c = fine_max(Sf, winner(m))
            errs.append(np.linalg.norm(p-mu)); cont.append(np.linalg.norm(c-mu))
    H = hess(Ft*np.conj(Ft)*W, np.zeros(2)); a = H[0,1]/H[0,0]; b = H[1,0]/H[1,1]
    M = np.array([[1,a],[b,1]]); g = NF/(NF-1)
    out[f'oracle_{wname}'] = dict(parabola_max=float(max(errs)), parabola_rms=float(np.sqrt(np.mean(np.square(errs)))),
        finegrid_max_err=float(max(cont)), H=H.tolist(), a=float(a), b=float(b), rho=float(H[0,1]/np.sqrt(H[0,0]*H[1,1])),
        eig_fixed_iteration=np.linalg.eigvals(np.eye(2)-M).tolist(),
        eig_sumothers_iteration=np.linalg.eigvals(np.eye(2)-g*M).tolist(),
        eig_sumothers_exactmax=float(1-g))
json.dump(out, open(sys.argv[2],'w'), indent=1); 
for k,v in out.items():
    print(k, {kk:(vv if not isinstance(vv,dict) else {x:y for x,y in vv.items() if x!='traj'}) for kk,vv in v.items() if kk not in('truth',)})
