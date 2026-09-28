#!/usr/bin/env python3
"""Issue 61: emit the B1 sensitivity certificate from the margin-calibrated control run.

Produced on cpu64 from `stageB_sensitivity_controls.json`, which is itself
`i61_analyse_B.py` run over the follow-up tree with the control arms.  The certificate is
consumed by `i61_analyse_B.py --sensitivity` (env `I61_SENSITIVITY_CERT`) on the 4GPUs tree,
where the real arms live.

A certificate is only meaningful if the two runs are the same computation.  That is not
assumed: the certificate carries the CPU-baseline half-map digests from both hosts, and the
consuming gate is expected to be read together with them.  If they differ, the certificate
must not be used.
"""
import hashlib, json, os, sys

CTRL_ROLE = {
    "ctrl_noise_f0062": "AT the harm margin: tests whether a harmful arm can earn a PASS (S1)",
    "ctrl_noise_f0076": "at the harm margin: locates the demonstrated detection boundary",
    "ctrl_noise_f011": "beyond the harm margin: must be rejected or B1 is not fit for purpose",
    "ctrl_noise_f020": "well beyond the harm margin: completes the PR #65 point-only control",
    "ctrl_noise_f005": "milder than the harm margin: cannot certify, retained for the response curve",
}


def mrc_payload_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        fh.seek(1024)
        while True:
            c = fh.read(1 << 22)
            if not c:
                break
            h.update(c)
    return h.hexdigest()


def main(root, stageb_json, out, peer_digests_json):
    res = json.load(open(stageb_json))
    margin = res["margins"]["B1_rho"]
    controls = []
    for a, entry in res["arms"].items():
        if not a.startswith("ctrl_"):
            continue      # a real arm may never be written into a certificate as a control
        jk = entry.get("held22_jackknife", {}).get("B1_rho_primary_corrected")
        if not jk or "error" in jk:
            pt = entry.get("held22", {}).get("B1_rho_primary_corrected", {}).get("value")
            controls.append({"control": a, "rho": pt, "upper95": None, "lower95": None,
                             "role": CTRL_ROLE.get(a, ""),
                             "why": "no jackknife interval; cannot certify"})
            continue
        controls.append({
            "control": a, "rho": jk["point_estimate"],
            "upper95": jk["upper95_one_sided"], "lower95": jk["lower95_one_sided"],
            "jackknife_se": jk["jackknife_se"], "jackknife_n": jk["jackknife_n"],
            "role": CTRL_ROLE.get(a, ""),
            "why": ("certifies B1: at or beyond the harm margin and rejected by the test"
                    if (jk["point_estimate"] <= margin and jk["upper95_one_sided"] < margin)
                    else "does not certify B1")})

    try:
        local = {h: mrc_payload_sha(f"{root}/rec/cpu/held22_half{h}_class001_unfil.mrc")
                 for h in (1, 2)}
    except FileNotFoundError as exc:
        print(f"ABORT: local CPU baseline half-map missing, equivalence cannot be proved: {exc}",
              file=sys.stderr)
        return 2
    if not os.path.exists(peer_digests_json):
        print(f"ABORT: peer digest file {peer_digests_json} absent; a certificate without an "
              "equivalence proof must not be produced", file=sys.stderr)
        return 2
    peer = json.load(open(peer_digests_json))
    agree = all(str(peer.get(str(h))) == local[h] for h in (1, 2))

    cert = {
        "source": "cpu64 margin-calibrated control run (docs/issue61_noninferiority)",
        "margin": margin,
        "controls": sorted(controls, key=lambda c: (c["rho"] is None, -(c["rho"] or 0))),
        "equivalence_proof": {
            "claim": ("the control run and the real-arm run are the same computation, so a "
                      "sensitivity statement proved on one transfers to the other"),
            "cpu_baseline_half_map_payload_sha256_this_host": local,
            "cpu_baseline_half_map_payload_sha256_peer_host": peer,
            "bit_identical": agree,
            "note": ("if bit_identical is not true the certificate must not be used to gate the "
                     "real-arm verdicts"),
        },
    }
    if not agree:
        print("ABORT: CPU baseline half-maps differ between hosts; the two runs are NOT the same "
              "computation and no certificate is written", file=sys.stderr)
        return 3
    json.dump(cert, open(out, "w"), indent=1, sort_keys=True)
    print(f"margin {margin}")
    for c in cert["controls"]:
        r = "-" if c["rho"] is None else f"{c['rho']:.5f}"
        u = "-" if c["upper95"] is None else f"{c['upper95']:.5f}"
        print(f"  {c['control']:20s} rho={r:>8s} upper95={u:>8s}  {c['why']}")
    print(f"cpu baseline bit-identical to peer host: {agree}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
