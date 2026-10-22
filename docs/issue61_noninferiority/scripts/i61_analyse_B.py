#!/usr/bin/env python3
"""Issue 61 Stage B analysis: matched-orientation reconstruction endpoints.

B1 (primary): rho = median over qualifying shells of SSNR_arm/SSNR_cpu.
B2          : resolution at FSC = 0.143 (RELION's reported value).
B3          : auto sharpening B-factor.
Uncertainty : delete-one-movie jackknife over the 22 held-out movies.

VALIDITY GATE (added after PR #65 review findings r4119264405 / r4119264412).
PROTOCOL.md requires that if the sensitivity control fails, every Stage B verdict becomes
INCONCLUSIVE.  The shipped version only stated that in prose and assigned real-arm verdicts
from each arm's own bound, so a rerun with an absent or insensitive control would still have
emitted PASS.  It is now enforced in code, and enforced against the right condition: a
control must be *rejected at the harm margin*, not merely be distinguishable from 1.

Measured rejection is descriptive: it does not independently establish that a control is
harmful.  Historical noise targets are unvalidated estimates, not known truth.  No accepted
forward harm model or coverage-validation policy is implemented here, so a certificate cannot
restore scientific PASS.  Its baseline payload digests must still bind to this local run before
its controls can be reported as identity-bound, unvalidated descriptive evidence.
"""
import glob, hashlib, json, math, os, sys
import numpy as np
from scipy.stats import t as tdist

ROOT = os.environ.get("I61_ROOT", "/home/alex/mc-issue61")
REAL = os.environ.get("I61_REAL", "cpu default allfftw").split()
CTRL = os.environ.get("I61_CTRL",
                      "ctrl_noise_f005 ctrl_noise_f020 ctrl_envelope_b20").split()
ALL = REAL + CTRL
# optional path to a sensitivity certificate from an equivalent run
SENSITIVITY_CERT = os.environ.get("I61_SENSITIVITY_CERT", "")
OUT_NAME = os.environ.get("I61_OUT", "stageB_reconstruction.json")
BAND = (8.0, 3.0)          # Angstrom, inclusive
FSC_FLOOR = 0.143          # qualifying shells need FSC_cpu >= this
MIN_SHELLS = 20
MARGIN = {"B1_rho": 0.95, "B2_d143_A": 0.05, "B3_bfactor_A2": -10.0}
FSC_COL_PRIMARY = "_rlnFourierShellCorrelationCorrected"
FSC_COL_ALT = "_rlnFourierShellCorrelationUnmaskedMaps"


def parse_pp(path):
    lines = open(path).read().splitlines()
    out = {"general": {}, "fsc": {}}
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s == "data_general":
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("data_"):
                f = lines[i].split()
                if len(f) == 2 and f[0].startswith("_rln"):
                    out["general"][f[0]] = f[1]
                i += 1
            continue
        if s == "data_fsc":
            j = i
            while not lines[j].strip().startswith("loop_"):
                j += 1
            k = j + 1
            cols = []
            while lines[k].strip().startswith("_rln"):
                cols.append(lines[k].strip().split()[0])
                k += 1
            rows = []
            while k < len(lines) and lines[k].strip() and not lines[k].strip().startswith("data_"):
                rows.append([float(x) for x in lines[k].split()])
                k += 1
            arr = np.array(rows)
            out["fsc"] = {c: arr[:, n] for n, c in enumerate(cols)}
            i = k
            continue
        i += 1
    return out


def ssnr(fsc):
    f = np.clip(fsc, -0.999, 0.999)
    return 2.0 * f / (1.0 - f)


def rho(pp_arm, pp_cpu, col):
    d = pp_cpu["fsc"]["_rlnAngstromResolution"]
    fc = pp_cpu["fsc"][col]
    fa = pp_arm["fsc"][col]
    q = (d <= BAND[0]) & (d >= BAND[1]) & (fc >= FSC_FLOOR)
    n = int(q.sum())
    if n < MIN_SHELLS:
        return None, n, 0
    r = ssnr(fa[q]) / ssnr(fc[q])
    return float(np.median(r)), n, int((fa[q] < 0).sum())


def load(arm, name):
    p = f"{ROOT}/pp/{arm}/{name}.star"
    return parse_pp(p) if os.path.exists(p) else None


def jk_bounds(theta_full, theta_reps):
    n = len(theta_reps)
    tr = np.asarray(theta_reps, float)
    mean = tr.mean()
    se = math.sqrt((n - 1) / n * np.sum((tr - mean) ** 2))
    tc = float(tdist.ppf(0.95, n - 1))
    bias = (n - 1) * (mean - theta_full)
    return {"jackknife_n": n, "jackknife_se": se,
            "jackknife_bias_estimate": bias,
            "lower95_one_sided": theta_full - tc * se,
            "upper95_one_sided": theta_full + tc * se,
            "ci95_two_sided": [theta_full - float(tdist.ppf(0.975, n - 1)) * se,
                               theta_full + float(tdist.ppf(0.975, n - 1)) * se]}


# The analysis set is FIXED by the protocol, not discovered from the filesystem.
# Review finding 4111302870: globbing pp/cpu/jk_*.star let a missing output silently shrink
# the jackknife (narrowing the bounds) and a stale file silently add a replicate.
ALL24 = ["00021", "00022", "00023", "00024", "00025", "00026", "00027", "00028",
         "00029", "00030", "00031", "00035", "00036", "00037", "00039", "00040",
         "00042", "00043", "00044", "00045", "00046", "00047", "00048", "00049"]
DEV = ["00021", "00046"]          # development movies, excluded from every primary result
held = [m for m in ALL24 if m not in DEV]
assert len(ALL24) == 24 and len(held) == 22, (len(ALL24), len(held))
_found = sorted(os.path.basename(p)[3:-5] for p in glob.glob(f"{ROOT}/pp/cpu/jk_*.star"))
if _found != held:
    raise SystemExit(
        "ABORT: the jackknife replicate set on disk does not match the preregistered 22 "
        f"held-out movies.\n  missing: {sorted(set(held) - set(_found))}\n"
        f"  unexpected: {sorted(set(_found) - set(held))}\n"
        "Refusing to compute confidence bounds from a different sample than the protocol fixes.")
res = {"band_A": BAND, "fsc_floor": FSC_FLOOR, "min_shells": MIN_SHELLS,
       "margins": MARGIN, "held_out_movies": held,
       "fsc_column_primary": FSC_COL_PRIMARY, "fsc_column_alt": FSC_COL_ALT,
       "arms": {}, "point_estimates": {}}

pp = {a: {n: load(a, n) for n in
          ["all24", "held22"] + [f"jk_{m}" for m in held]} for a in ALL}

for a in ALL:
    res["point_estimates"][a] = {}
    for s in ("all24", "held22"):
        g = pp[a][s]
        if g is None:
            continue
        res["point_estimates"][a][s] = {
            "d143_A": float(g["general"]["_rlnFinalResolution"]),
            "bfactor_A2": float(g["general"]["_rlnBfactorUsedForSharpening"]),
        }

for a in ALL:
    if a == "cpu":
        continue
    res["arms"][a] = {}
    for s in ("held22", "all24"):
        if pp[a].get(s) is None or pp["cpu"].get(s) is None:
            continue
        entry = {}
        for tag, col in (("primary_corrected", FSC_COL_PRIMARY), ("alt_unmasked", FSC_COL_ALT)):
            r, nsh, nneg = rho(pp[a][s], pp["cpu"][s], col)
            entry[f"B1_rho_{tag}"] = {"value": r, "n_shells": nsh, "n_negative_arm_fsc": nneg}
        entry["B2_d143_delta_A"] = (res["point_estimates"][a][s]["d143_A"]
                                    - res["point_estimates"]["cpu"][s]["d143_A"])
        entry["B3_bfactor_delta_A2"] = (res["point_estimates"][a][s]["bfactor_A2"]
                                        - res["point_estimates"]["cpu"][s]["bfactor_A2"])
        res["arms"][a][s] = entry

    # delete-one-movie jackknife, held-out set only.  Incompleteness is recorded, never
    # silently absorbed into a narrower interval (review finding 4111302870).
    _miss = ([m for m in held if not pp[a].get(f"jk_{m}")]
             + [m for m in held if not pp["cpu"].get(f"jk_{m}")])
    if _miss:
        res["arms"][a]["held22_jackknife_unavailable"] = {
            "reason": "missing post-processing output for some replicates",
            "missing_replicates": sorted(set(_miss))}
    if not _miss:
        reps = {"B1_rho_primary_corrected": [], "B1_rho_alt_unmasked": [],
                "B2_d143_delta_A": [], "B3_bfactor_delta_A2": []}
        for m in held:
            k = f"jk_{m}"
            reps["B1_rho_primary_corrected"].append(rho(pp[a][k], pp["cpu"][k], FSC_COL_PRIMARY)[0])
            reps["B1_rho_alt_unmasked"].append(rho(pp[a][k], pp["cpu"][k], FSC_COL_ALT)[0])
            reps["B2_d143_delta_A"].append(float(pp[a][k]["general"]["_rlnFinalResolution"])
                                           - float(pp["cpu"][k]["general"]["_rlnFinalResolution"]))
            reps["B3_bfactor_delta_A2"].append(float(pp[a][k]["general"]["_rlnBfactorUsedForSharpening"])
                                               - float(pp["cpu"][k]["general"]["_rlnBfactorUsedForSharpening"]))
        jk = {}
        full = res["arms"][a].get("held22")
        if full is None:
            res["arms"][a]["held22_jackknife_unavailable"] = {
                "reason": "no held22 result for this arm, so no paired jackknife is defined"}
            full = {}
        for key, vals in reps.items():
            if any(v is None for v in vals):
                jk[key] = {"error": "some replicates had too few qualifying shells"}
                continue
            pt = (full.get(key, {}).get("value") if key.startswith("B1") else full.get(key))
            if pt is None:
                jk[key] = {"error": "no full-sample point estimate; endpoint not computable"}
                continue
            b = jk_bounds(pt, vals)
            b["point_estimate"] = pt
            b["replicates"] = vals
            if key.startswith("B1"):
                b["margin"] = MARGIN["B1_rho"]
                b["verdict"] = ("PASS" if b["lower95_one_sided"] >= MARGIN["B1_rho"] else
                                "FAIL" if b["upper95_one_sided"] < MARGIN["B1_rho"] else "INCONCLUSIVE")
                b["rule"] = f"lower one-sided 95% bound of rho >= {MARGIN['B1_rho']}"
            elif key.startswith("B2"):
                b["margin"] = MARGIN["B2_d143_A"]
                b["verdict"] = ("PASS" if b["upper95_one_sided"] <= MARGIN["B2_d143_A"] else
                                "FAIL" if b["lower95_one_sided"] > MARGIN["B2_d143_A"] else "INCONCLUSIVE")
                b["rule"] = f"upper one-sided 95% bound of (arm-cpu) <= {MARGIN['B2_d143_A']} A"
            else:
                b["margin"] = MARGIN["B3_bfactor_A2"]
                b["verdict"] = ("PASS" if b["lower95_one_sided"] >= MARGIN["B3_bfactor_A2"] else
                                "FAIL" if b["upper95_one_sided"] < MARGIN["B3_bfactor_A2"] else "INCONCLUSIVE")
                b["rule"] = f"lower one-sided 95% bound of (arm-cpu) >= {MARGIN['B3_bfactor_A2']} A^2"
            jk[key] = b
        res["arms"][a]["held22_jackknife"] = jk

# --------------------------------------------------------------------------------------
# Validity precondition.  See PROTOCOL.md Amendments 1 and 2 and CERTIFICATE_VALIDATION.md.
# Identity binding is necessary, but neither identity nor a JSON assertion validates science.
# --------------------------------------------------------------------------------------
CONTROL_PREFIX = "ctrl_"


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def local_baseline_digests():
    """Historical certificate convention: SHA-256 over bytes 1024+ (labels excluded)."""
    digests = {}
    for half in ("1", "2"):
        path = f"{ROOT}/rec/cpu/held22_half{half}_class001_unfil.mrc"
        h = hashlib.sha256()
        size = 0
        with open(path, "rb") as fh:
            fh.seek(1024)
            for chunk in iter(lambda: fh.read(1 << 22), b""):
                h.update(chunk)
                size += len(chunk)
        if not size:
            raise ValueError(f"empty or truncated CPU baseline payload: {path}")
        digests[half] = h.hexdigest()
    return digests


def load_certificate(path, margin):
    """Return identity-bound descriptive entries, never scientific certification.

    This validates structure and local identity only.  Remote provenance, control truth and
    coverage cannot be authenticated by self-reported certificate fields.
    """
    def reject(reason):
        return [], {"used": False, "path": path, "reason": reason,
                    "identity_binding_verified": False, "scientific_certification_accepted": False}

    if not path:
        return reject("no certificate supplied")
    try:
        with open(path) as fh:
            cert = json.load(fh)
    except (OSError, ValueError) as exc:
        return reject(f"certificate is not readable JSON: {exc}")
    if not isinstance(cert, dict):
        return reject("certificate must be a JSON object")
    proof = cert.get("equivalence_proof")
    if not isinstance(proof, dict):
        return reject("equivalence_proof must be an object")
    if proof.get("bit_identical") is not True:
        return reject("equivalence_proof.bit_identical must be true; insufficient identity evidence")
    if not finite_number(cert.get("margin")) or cert["margin"] != margin:
        return reject(f"certificate margin {cert.get('margin')!r} != analysis margin {margin}")
    for key in ("cpu_baseline_half_map_payload_sha256_this_host",
                "cpu_baseline_half_map_payload_sha256_peer_host"):
        hashes = proof.get(key)
        if not isinstance(hashes, dict) or any(
                not isinstance(hashes.get(h), str) or len(hashes[h]) != 64
                or any(ch not in "0123456789abcdef" for ch in hashes[h]) for h in ("1", "2")):
            return reject(f"{key} must contain both half-map SHA-256 digests")
    try:
        local = local_baseline_digests()
    except (OSError, ValueError) as exc:
        return reject(f"local CPU baseline digest binding unavailable: {exc}")
    for key in ("cpu_baseline_half_map_payload_sha256_this_host",
                "cpu_baseline_half_map_payload_sha256_peer_host"):
        if any(proof[key][h] != local[h] for h in ("1", "2")):
            return reject(f"{key} digest mismatch against recomputed local CPU baseline payloads")
    controls = cert.get("controls")
    if not isinstance(controls, list):
        return reject("certificate controls must be a list")
    out = []
    seen = set()
    for c in controls:
        if (not isinstance(c, dict) or not isinstance(c.get("control"), str)
                or not c["control"].startswith(CONTROL_PREFIX) or c["control"] in seen):
            return reject("certificate controls must have unique ctrl_ names; real arms cannot certify")
        seen.add(c["control"])
        values = [c.get(k) for k in ("lower95", "rho", "upper95")]
        if any(v is not None and not finite_number(v) for v in values):
            return reject(f"non-finite or non-numeric control estimate/interval: {c['control']}")
        lower, point, upper = values
        if ((lower is not None and (point is None or lower > point))
                or (upper is not None and (point is None or upper < point))):
            return reject(f"unordered control interval: {c['control']}")
        out.append({"control": c.get("control"), "source": cert.get("source", path),
                    "rho": c.get("rho"), "upper95": c.get("upper95"), "lower95": c.get("lower95"),
                    "certificate_designed_rho_unvalidated": c.get("designed_rho"), "why": ""})
    return out, {"used": True, "path": path, "n_controls": len(out),
                 "use": "identity-bound descriptive evidence only",
                 "identity_binding_verified": True, "local_cpu_baseline_payload_sha256": local,
                 "scientific_certification_accepted": False,
                 "coverage_demonstration_unvalidated": cert.get("coverage_demonstration"),
                 "equivalence_proof": proof}


def control_candidates(res, cert_entries):
    """Declared controls plus identity-bound, unvalidated certificate entries."""
    out = []
    for a, entry in res["arms"].items():
        if not a.startswith(CONTROL_PREFIX):
            continue                      # real arms may never certify anything
        jk = entry.get("held22_jackknife", {}).get("B1_rho_primary_corrected")
        if not jk or "error" in jk:
            pt = entry.get("held22", {}).get("B1_rho_primary_corrected", {}).get("value")
            out.append({"control": a, "source": "this run", "rho": pt,
                        "upper95": None, "lower95": None, "designed_rho": None,
                        "why": "no jackknife interval, so the endpoint cannot be shown to reject it"})
            continue
        out.append({"control": a, "source": "this run", "rho": jk["point_estimate"],
                    "upper95": jk["upper95_one_sided"], "lower95": jk["lower95_one_sided"],
                    "designed_rho": HISTORICAL_RHO_TARGETS.get(a), "why": ""})
    for c in cert_entries:
        c = dict(c)
        # Certificate assertions cannot replace even the historical reference targets.
        c["designed_rho"] = HISTORICAL_RHO_TARGETS.get(c.get("control"))
        out.append(c)
    return out


# Historical targets, retained for description, NOT accepted control truth.  The noise model
# was contradicted and fitted; prospective thinning truth is also not accepted here.
HISTORICAL_RHO_TARGETS = {"ctrl_noise_f005": 0.952, "ctrl_noise_f0062": 0.950, "ctrl_noise_f0076": 0.950,
                "ctrl_noise_f011": 0.929, "ctrl_noise_f020": 0.833, "ctrl_envelope_b20": 1.000}

MARGIN_B1 = MARGIN["B1_rho"]
cert_entries, cert_status = load_certificate(SENSITIVITY_CERT, MARGIN_B1)
cands = control_candidates(res, cert_entries)

for c in cands:
    at_harm = finite_number(c["rho"]) and c["rho"] <= MARGIN_B1
    c["at_or_beyond_harm_measured"] = at_harm
    c["design_validated"] = False
    c["design_validation_reason"] = "no accepted independent forward harm model; historical targets are not truth"
    c["designed_at_or_beyond_harm"] = False
    c["rejected_at_margin"] = bool(at_harm and finite_number(c["upper95"])
                                   and c["upper95"] < MARGIN_B1)
    c["earned_a_pass"] = (None if not finite_number(c["lower95"]) else bool(c["lower95"] >= MARGIN_B1))
    c["why"] = ("measured rejection only; does not certify B1 without validated control truth"
                if c["rejected_at_margin"] else "does not establish sensitivity at the harm margin")

# Preserve observed rejection as description, distinct from independently known harm.
measured_rejections = [c for c in cands if c["rejected_at_margin"]]
observed_boundary = max(measured_rejections, key=lambda c: c["rho"], default=None)
certifying = [c for c in measured_rejections if c["design_validated"] and c["designed_at_or_beyond_harm"]]
boundary = max(certifying, key=lambda c: c["rho"], default=None)

# S1 -- can a harmful arm earn a PASS?  Informative ONLY for a control designed at or beyond
# the margin whose measured rho landed ABOVE it; otherwise non-passing is arithmetic, not evidence.
s1_informative = [c for c in cands if c["designed_at_or_beyond_harm"]
                  and c["rho"] is not None and c["rho"] > MARGIN_B1
                  and c["lower95"] is not None]
s1_failures = [c for c in s1_informative if c["earned_a_pass"]]
s1_state = ("FAILED" if s1_failures else "PASSED" if s1_informative else "UNTESTED")

# Amendment 2 additionally requires validated coverage.  An upper bound cannot reject when
# the sample point equals the margin; that says nothing about a control's unknown true rho.
coverage = cert_status.get("coverage_demonstration_unvalidated")
coverage_validation = {
    "status": "UNVALIDATED", "accepted": False,
    "reason": ("no maintainer-approved coverage/operating-characteristic validation policy is "
               "implemented; supplied coverage assertions cannot establish margin sensitivity")}

res["validity"] = {
    "rule": ("PROTOCOL Amendment 1 requires a control at or beyond the harm margin to be "
             "positively rejected (S2).  Amendment 2 additionally requires a coverage "
             "demonstration at the margin before a real-arm PASS may stand.  Measured rejection "
             "cannot define control truth, and historical targets cannot validate S1 or S2."),
    "margin": MARGIN_B1,
    "candidates": cands,
    "certificate": cert_status,
    "S2_sensitivity_demonstrated": bool(certifying),
    "S2_certifying_controls": [c["control"] for c in certifying],
    "S2_measured_rejections_unvalidated": [c["control"] for c in measured_rejections],
    "observed_rejection_boundary_rho_unvalidated": (observed_boundary["rho"] if observed_boundary else None),
    "demonstrated_detection_boundary_rho": (boundary["rho"] if boundary else None),
    "S2_rejection_when_point_equals_margin_is_unattainable_by_construction": True,
    "S1_state": s1_state,
    "S1_informative_controls": [c["control"] for c in s1_informative],
    "S1_note": ("lower95 <= rho by construction, so a control measuring at or below the margin "
                "cannot pass; only a margin-designed control measuring ABOVE the margin tests S1"),
    "coverage_demonstration_at_margin": coverage,
    "coverage_validation": coverage_validation,
}

margin_sensitivity_proven = bool(certifying) and coverage_validation["accepted"]
res["validity"]["margin_sensitivity_proven"] = margin_sensitivity_proven
res["validity"]["sensitivity_demonstrated"] = margin_sensitivity_proven

if not margin_sensitivity_proven:
    reason = (f"sensitivity AT the {MARGIN_B1} harm margin is UNPROVEN: no accepted independent "
              "forward harm model validates control truth, and no maintainer-approved coverage/"
              "operating-characteristic validation policy is implemented.  Measured rejection, "
              "historical targets and certificate assertions are descriptive only.  Real-arm "
              "Stage B verdicts remain INCONCLUSIVE under PROTOCOL Amendment 2.")
    res["validity"]["forced_inconclusive"] = True
    res["validity"]["reason"] = reason
    for a in REAL:
        if a == "cpu" or a not in res["arms"]:
            continue
        for key, b in res["arms"][a].get("held22_jackknife", {}).items():
            if isinstance(b, dict) and "verdict" in b:
                b["verdict_before_validity_gate"] = b["verdict"]
                b["verdict"] = "INCONCLUSIVE"
                b["validity_override"] = reason
else:
    res["validity"]["forced_inconclusive"] = False

os.makedirs(f"{ROOT}/results", exist_ok=True)
json.dump(res, open(f"{ROOT}/results/{OUT_NAME}", "w"), indent=1, sort_keys=True,
          default=lambda o: None if o is None else float(o))

v = res["validity"]
print("margin sensitivity proven:", v["margin_sensitivity_proven"])
print(f"   S2 rejection demonstrated : {v['S2_sensitivity_demonstrated']}"
      f"  (boundary rho = {v['demonstrated_detection_boundary_rho']})")
print(f"   S1 (no harmful arm passes): {v['S1_state']}  {v['S1_note']}")
print(f"   coverage demo at margin   : {v['coverage_demonstration_at_margin']}")
print(f"   certificate               : {v['certificate']}")
for c in v["candidates"]:
    r = "-" if c["rho"] is None else f"{c['rho']:.5f}"
    u = "-" if c["upper95"] is None else f"{c['upper95']:.5f}"
    print(f"   control {c['control']:20s} rho={r:>8s} upper95={u:>8s}"
          f" measured_rejection={c['rejected_at_margin']}  [{c['source']}] {c['why']}")
if not v["margin_sensitivity_proven"]:
    print("   -> every real-arm Stage B verdict withdrawn to INCONCLUSIVE")
print()
print("point estimates (matched-orientation reconstruction)")
print(f"{'arm':18s} {'set':7s} {'d143 A':>8s} {'Bsharp':>9s}")
for a in ALL:
    for s in ("held22", "all24"):
        pe = res["point_estimates"].get(a, {}).get(s)
        if pe:
            print(f"{a:18s} {s:7s} {pe['d143_A']:8.3f} {pe['bfactor_A2']:9.2f}")
print()
print(f"{'arm':18s} {'endpoint':28s} {'point':>9s} {'95% bound':>10s} {'margin':>8s}  verdict")
for a in ALL:
    if a == "cpu":
        continue
    jk = res["arms"][a].get("held22_jackknife")
    if not jk:
        e = res["arms"][a].get("held22", {})
        r = e.get("B1_rho_primary_corrected", {}).get("value")
        print(f"{a:18s} {'B1_rho (no jackknife)':28s} {r if r is None else round(r,5)!s:>9s} "
              f"{'-':>10s} {MARGIN['B1_rho']:8.2f}  POINT-ONLY")
        continue
    for k, v in jk.items():
        if "error" in v:
            print(f"{a:18s} {k:28s}  {v['error']}")
            continue
        b = v["lower95_one_sided"] if "B1" in k or "B3" in k else v["upper95_one_sided"]
        print(f"{a:18s} {k:28s} {v['point_estimate']:9.5f} {b:10.5f} {v['margin']:8.2f}  {v['verdict']}")
