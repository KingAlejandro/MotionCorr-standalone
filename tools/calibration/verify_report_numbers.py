#!/usr/bin/env python3
"""Re-derive every load-bearing number quoted in the issue #60 report.

Run from the repository root:

    python3 tools/calibration/verify_report_numbers.py

Exits non-zero if any number in docs/calibration/issue60_gate_calibration.md
drifts from what docs/calibration/data/*.json actually contains. It exists so a
reviewer does not have to take the prose on trust, and so a later edit to the
data cannot silently invalidate the report.
"""
import sys, glob, math, statistics as st
from pathlib import Path
sys.path.insert(0,'.')
from tools.calibration import analyze as A
paths=[Path(p) for p in glob.glob("docs/calibration/data/layer*.json")]
l1=A.load([p for p in paths if 'layer1' in p.name]); l2=A.load([p for p in paths if 'layer2' in p.name]); l3=A.load([p for p in paths if 'layer3' in p.name])
allr=l1+l2+l3; floors=A.noise_floor(l3)["j4"]
ok=[]
def chk(claim, got, want, tol=0.02):
    good = abs(got-want) <= tol*max(abs(want),1e-12) if want else abs(got)<=tol
    ok.append(good)
    print(f"[{'OK ' if good else 'BAD'}] {claim}: report {want}, data {got}")

# 1. harmless floor
harmless=[r for r in l3 if r.get("group") in ("REF","H1_threads","H2_proc_bind","H3_repeat") or r.get("label") in ("gain_null","mov_null")]
vals=[abs(A.get(r,d)) for r in harmless for d in
      ("image_relative_rmse","image_rmse","image_max_abs_error","std_delta_b_a2","std_eps_incoherent",
       "std_shift_px","std_scale_dev","traj_max_shift_error","traj_coord_rms_error","field_rms_px")
      if A.get(r,d) is not None]
chk("harmless cell count", len(harmless), 176, 0)
print(f"      harmless cells = {len(harmless)}, max |value| = {max(vals):.3e}")
chk("largest harmless value <= 1.5e-15", max(vals), 1.478e-15, 0.05)

# 2. tier census
census={}
for r in allr:
    t=A.tier_of(r,"harm_delta_b_a2",5.0,floors); census[t]=census.get(t,0)+1
print("      census:", census)
chk("negligible cells", census["negligible"], 481, 0)
chk("total cells", len(allr), 1129, 0)

# 3. relative RMSE overlap
neg=[r for r in allr if A.tier_of(r,"harm_delta_b_a2",5.0,floors)=="negligible"]
bad=[r for r in allr if A.tier_of(r,"harm_delta_b_a2",5.0,floors).startswith("unacceptable")]
chk("max relRMSE on negligible", max(abs(A.get(r,"image_relative_rmse")) for r in neg if A.get(r,"image_relative_rmse") is not None), 4.884, 0.01)
over=sum(1 for r in neg if (A.get(r,"image_relative_rmse") or 0)>0.001)
chk("negligible cells exceeding 0.001 (fraction)", over/len(neg), 0.578, 0.01)

# 4. delta-B separation
mn=max(abs(A.get(r,"std_delta_b_a2")) for r in neg if A.get(r,"std_delta_b_a2") is not None)
mb=min(abs(A.get(r,"std_delta_b_a2")) for r in bad
       if A.get(r,"std_delta_b_a2") is not None and A.tier_of(r,"harm_delta_b_a2",5.0,floors)=="unacceptable:envelope")
chk("max dB on negligible", mn, 1.705, 0.01); chk("min dB on unacceptable envelope", mb, 5.004, 0.01)
chk("dB clean band", mb/mn, 2.93, 0.02)

# 5. shift clean band
def f(r): return str(r.get("fault") or r.get("group") or "")
chk("max shift on negligible non-translation", max(abs(A.get(r,"std_shift_px")) for r in neg if "X1" not in f(r) and A.get(r,"std_shift_px") is not None), 1.42e-2, 0.02)

# 6. panel
sel=[r for r in allr if r.get("split") in (None,"selection","control")]; hold=[r for r in allr if r.get("split")=="holdout"]
c=A.panel_coverage(hold,{"std_delta_b_a2":2.0,"std_shift_px":0.05,"std_scale_dev":1e-2},"harm_delta_b_a2",5.0,floors)
chk("hold-out detection", c["caught"], 270, 0); chk("hold-out false alarms", c["false_alarms"], 0, 0)

# 7. L1 key rows
def l1row(flt,sev,key):
    v=[abs(A.get(r,key)) for r in l1 if r["fault"]==flt and abs(r["severity"]-sev)<1e-9 and A.get(r,key) is not None]
    return st.median(v)
chk("L1 translation 0.1px relRMSE", l1row("X1_translation_px",0.1,"image_relative_rmse"), 0.1681, 0.005)
chk("L1 translation 0.1px dB ~ 0", l1row("X1_translation_px",0.1,"std_delta_b_a2"), 0.0, 1e-12)
chk("L1 jitter 0.4px dB", l1row("X2_jitter_sigma_px",0.4,"std_delta_b_a2"), 9.911, 0.01)
chk("L1 applied dB 5 recovered", l1row("X5_applied_delta_b_a2",5.0,"std_delta_b_a2"), 5.004, 0.005)
chk("L1 jitter 0.02px relRMSE", l1row("X2_jitter_sigma_px",0.02,"image_relative_rmse"), 0.001441, 0.01)
chk("L1 jitter 0.02px dB", l1row("X2_jitter_sigma_px",0.02,"std_delta_b_a2"), 0.02507, 0.01)

# 8. the 0.001 extrapolation
r0=l1row("X2_jitter_sigma_px",0.02,"image_relative_rmse"); b0=l1row("X2_jitter_sigma_px",0.02,"std_delta_b_a2")
chk("dB at relRMSE=0.001 via jitter", b0*(0.001/r0), 0.017, 0.10)
r1=l1row("X3_drift_total_px",0.05,"image_relative_rmse"); b1=l1row("X3_drift_total_px",0.05,"std_delta_b_a2")
chk("dB at relRMSE=0.001 via drift", b1*(0.001/r1), 0.014, 0.10)
r2=l1row("X5_applied_delta_b_a2",1.0,"image_relative_rmse")
chk("dB at relRMSE=0.001 via envelope", 1.0*(0.001/r2), 0.018, 0.10)

# 9. L3 headline cells
def l3cell(label,key):
    v=[abs(A.get(r,key)) for r in l3 if r.get("label")==label and A.get(r,key) is not None]
    return max(v) if v else float('nan')
chk("L3 translated movie relRMSE", l3cell("mov_shift2_gplus","image_relative_rmse"), 1.399, 0.005)
chk("L3 translated movie dB", l3cell("mov_shift2_gplus","std_delta_b_a2"), 0.103, 0.05)
chk("L3 translated movie shift", l3cell("mov_shift2_gplus","std_shift_px"), 2.850, 0.01)
chk("L3 translated movie trajmax == 0", l3cell("mov_shift2_gplus","traj_max_shift_error"), 0.0, 1e-12)
chk("L3 gain 1e-6 relRMSE", l3cell("gain_1e-06","image_relative_rmse"), 2.037e-3, 0.01)
chk("L3 gain 1e-6 dB", l3cell("gain_1e-06","std_delta_b_a2"), 3.813e-4, 0.02)
chk("L3 gain 1e-1 scale_dev", l3cell("gain_1e-01","std_scale_dev"), 0.1, 0.01)
chk("L3 dose 0.5 dB", l3cell("dose_0.5","std_delta_b_a2"), 3.551, 0.01)

print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)
