#!/usr/bin/env python3
"""Small, synthetic subprocess controls; no reconstruction or scientific qualification.

Use --expect-legacy-holes only with the pinned 45f07f14 analyser, before the fix.
All inputs/outputs live in a disposable temporary directory. --out writes a NEW report.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS")
HELD = ("00022 00023 00024 00025 00026 00027 00028 00029 00030 00031 "
        "00035 00036 00037 00039 00040 00042 00043 00044 00045 00047 00048 00049").split()


def pp_star(ratio, resolution=3.2, bfactor=-50):
    # CPU FSC .5 -> SSNR 2; invert SSNR for exactly the requested arm/CPU ratio.
    fsc = ratio / (1 + ratio)
    return (f"data_general\n_rlnFinalResolution {resolution}\n"
            f"_rlnBfactorUsedForSharpening {bfactor}\n\ndata_fsc\nloop_\n"
            "_rlnAngstromResolution #1\n_rlnFourierShellCorrelationCorrected #2\n"
            "_rlnFourierShellCorrelationUnmaskedMaps #3\n" +
            "".join(f"{3 + i * .2:.1f} {fsc:.17g} {fsc:.17g}\n" for i in range(24)) + "\n")


def endpoints(result):
    # Compare all descriptive fields, not just the verdicts that intentionally change.
    arms = copy.deepcopy(result["arms"])
    for entry in arms.values():
        for endpoint in entry.get("held22_jackknife", {}).values():
            for key in ("verdict", "verdict_before_validity_gate", "validity_override"):
                endpoint.pop(key, None)
    return {"arms": arms, "point_estimates": result["point_estimates"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--analyser", type=Path, default=Path(__file__).with_name("i61_analyse_B.py"))
    ap.add_argument("--expect-legacy-holes", action="store_true")
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    report = {"python": sys.executable, "analyser_sha256": hashlib.sha256(args.analyser.read_bytes()).hexdigest(),
              "threads": {k: "1" for k in THREADS}, "mode": "legacy-reproduction" if args.expect_legacy_holes else "regression",
              "cases": {}}
    with tempfile.TemporaryDirectory(prefix="i61-certificate-host-") as tmp:
        root = Path(tmp)
        for arm, ratio, resolution, bfactor in (("cpu", 1., 3.2, -50),
                                                ("default", .9999, 3.21, -51),
                                                ("allfftw", .99998, 3.19, -49)):
            folder = root / "pp" / arm
            folder.mkdir(parents=True)
            for name in ["held22", "all24"] + ["jk_" + m for m in HELD]:
                shift = (HELD.index(name[3:]) - 10.5) if name.startswith("jk_") else 0
                # Nonzero paired uncertainty in all endpoints; CPU stays constant.
                shift *= arm != "cpu"
                (folder / (name + ".star")).write_text(
                    pp_star(ratio + shift * 1e-6, resolution + shift * 1e-5, bfactor + shift * 1e-4))
        maps = root / "rec/cpu"
        maps.mkdir(parents=True)
        digests = {}
        for half in (1, 2):
            header = bytearray(1024)
            struct.pack_into("<4i", header, 0, 2, 2, 1, 2)
            payload = struct.pack("<4f", half, 2, 3, 4)
            (maps / f"held22_half{half}_class001_unfil.mrc").write_bytes(header + payload)
            digests[str(half)] = hashlib.sha256(payload).hexdigest()
        certificate = {"margin": .95, "source": "synthetic host control, NOT scientific evidence",
                       "equivalence_proof": {"bit_identical": True,
                           "cpu_baseline_half_map_payload_sha256_this_host": dict(digests),
                           "cpu_baseline_half_map_payload_sha256_peer_host": dict(digests)},
                       "controls": [{"control": "ctrl_noise_f011", "rho": .90,
                                     "lower95": .89, "upper95": .91, "designed_rho": .929}],
                       "coverage_demonstration": "yes"}

        def run(name, cert):
            env = {**os.environ, **{k: "1" for k in THREADS}, "I61_ROOT": str(root),
                   "I61_REAL": "cpu default allfftw", "I61_CTRL": "", "I61_OUT": name + ".json",
                   "I61_SENSITIVITY_CERT": ""}
            if cert is not None:
                path = root / (name + "-certificate.json")
                path.write_text(json.dumps(cert))
                env["I61_SENSITIVITY_CERT"] = str(path)
            proc = subprocess.run([sys.executable, str(args.analyser.resolve())], env=env,
                                  text=True, capture_output=True, timeout=30)
            assert proc.returncode == 0, (name, proc.returncode, proc.stderr)
            res = json.loads((root / "results" / (name + ".json")).read_text())
            v = res["validity"]
            report["cases"][name] = {"exit_code": proc.returncode,
                "margin_sensitivity_proven": v["margin_sensitivity_proven"],
                "certificate_used": v["certificate"]["used"],
                "certificate_reason": v["certificate"].get("reason"),
                "real_verdicts": {a: {k: b.get("verdict") for k, b in res["arms"][a]["held22_jackknife"].items()}
                                  for a in ("default", "allfftw")}}
            if not args.expect_legacy_holes:
                assert not v["margin_sensitivity_proven"], name
                assert all(b["verdict"] == "INCONCLUSIVE" for a in ("default", "allfftw")
                           for b in res["arms"][a]["held22_jackknife"].values()), name
            return res

        cases = {"truthy_coverage_string": certificate}
        bad_counts = copy.deepcopy(certificate)
        bad_counts["coverage_demonstration"] = {"n": 20, "false_pass": 20}
        cases["truthy_coverage_counts"] = bad_counts
        mismatch = copy.deepcopy(certificate)
        for key in ("cpu_baseline_half_map_payload_sha256_this_host", "cpu_baseline_half_map_payload_sha256_peer_host"):
            mismatch["equivalence_proof"][key] = {"1": "0" * 64, "2": "0" * 64}
        cases["mismatched_local_digests"] = mismatch
        envelope = copy.deepcopy(certificate)
        envelope["controls"][0].update(control="ctrl_envelope_b20", designed_rho=1.)
        cases["measured_only_harm"] = envelope
        override = copy.deepcopy(envelope)
        override["controls"][0]["designed_rho"] = .9
        cases["overridden_design"] = override
        results = {name: run(name, cert) for name, cert in cases.items()}
        absent = run("absent_certificate", None)
        numeric = endpoints(absent)
        report["legacy_endpoints_sha256"] = hashlib.sha256(
            json.dumps(numeric, sort_keys=True, allow_nan=False).encode()).hexdigest()
        report["synthetic_endpoint_summary"] = {a: {
            k: {key: value for key, value in b.items() if key in
                ("point_estimate", "jackknife_se", "lower95_one_sided", "upper95_one_sided")}
            for k, b in absent["arms"][a]["held22_jackknife"].items()}
            for a in ("default", "allfftw")}
        for name, res in results.items():
            assert endpoints(res) == numeric, name
        assert not absent["validity"]["margin_sensitivity_proven"]
        if args.expect_legacy_holes:
            assert all(res["validity"]["margin_sensitivity_proven"] for res in results.values())
            assert results["overridden_design"]["validity"]["candidates"][0]["designed_rho"] == .9
        else:
            for name in ("truthy_coverage_string", "truthy_coverage_counts", "measured_only_harm", "overridden_design"):
                assert results[name]["validity"]["certificate"]["identity_binding_verified"], name
                assert results[name]["validity"]["coverage_validation"]["status"] == "UNVALIDATED", name
            assert not results["mismatched_local_digests"]["validity"]["certificate"]["used"]
            assert "digest" in results["mismatched_local_digests"]["validity"]["certificate"]["reason"]
            for name in ("measured_only_harm", "overridden_design"):
                c = results[name]["validity"]["candidates"][0]
                assert c["designed_rho"] == 1. and not c["designed_at_or_beyond_harm"], name
            for res in results.values():
                assert not res["validity"]["certificate"].get("scientific_certification_accepted", False)
                assert not res["validity"]["S2_sensitivity_demonstrated"]
                assert res["validity"]["S1_state"] == "UNTESTED"
            # Removing map files or supplying malformed certificates must also fail closed.
            for name, mutate in (
                ("not_an_object", lambda c: []),
                ("invalid_proof", lambda c: {**c, "equivalence_proof": "yes"}),
                ("invalid_margin", lambda c: {**c, "margin": "yes"}),
                ("invalid_controls", lambda c: {**c, "controls": {"ctrl_fake": {}}}),
                ("nonfinite_rho", lambda c: {**c, "controls": [{**c["controls"][0], "rho": float("nan")}]}),
                ("unordered_interval", lambda c: {**c, "controls": [{**c["controls"][0], "lower95": .99}]}),
                ("missing_digests", lambda c: {**c, "equivalence_proof": {"bit_identical": True}})):
                res = run(name, mutate(copy.deepcopy(certificate)))
                assert not res["validity"]["certificate"]["used"], name
            for key in ("cpu_baseline_half_map_payload_sha256_this_host", "cpu_baseline_half_map_payload_sha256_peer_host"):
                cert = copy.deepcopy(certificate)
                other = next(k for k in cert["equivalence_proof"] if k != key and k.endswith("host"))
                untouched = dict(cert["equivalence_proof"][other])
                cert["equivalence_proof"][key]["2"] = "0" * 64
                assert cert["equivalence_proof"][other] == untouched, "hash-set fixture alias"
                status = run("mismatch_" + key, cert)["validity"]["certificate"]
                assert not status["used"] and status["reason"].startswith(key), (key, status)
            half1 = maps / "held22_half1_class001_unfil.mrc"
            original = half1.read_bytes()
            header_change = bytearray(original)
            header_change[224:229] = b"label"
            half1.write_bytes(header_change)
            assert run("label_only_change", certificate)["validity"]["certificate"]["identity_binding_verified"]
            half1.write_bytes(original[:-1] + b"x")
            assert not run("mutated_local_payload", certificate)["validity"]["certificate"]["used"]
            half1.write_bytes(original[:1024])
            assert not run("empty_local_payload", certificate)["validity"]["certificate"]["used"]
            half1.unlink()
            assert not run("missing_local_map", certificate)["validity"]["certificate"]["used"]
        if args.baseline:
            baseline = json.loads(args.baseline.read_text())
            assert baseline["legacy_endpoints_sha256"] == report["legacy_endpoints_sha256"], "legacy endpoint drift"
            report["baseline_analyser_sha256"] = baseline["analyser_sha256"]
        # Replay the retained full-sample FSC export through the actual parser/estimator.
        # Jackknives remain synthetic: this does NOT reanalyse historical raw maps or intervals.
        evidence = Path(__file__).resolve().parents[1] / "results"
        curves = json.loads((evidence / "fsc_curves.json").read_text())["sets"]
        historic = json.loads((evidence / "stageB_reconstruction.json").read_text())
        for subset in ("held22", "all24"):
            for arm in ("cpu", "default", "allfftw"):
                f = curves[subset][arm]
                rows = zip(f["AngstromResolution"], f["_rlnFourierShellCorrelationCorrected"],
                           f["_rlnFourierShellCorrelationUnmaskedMaps"])
                text = (f"data_general\n_rlnFinalResolution {f['FinalResolution']}\n"
                        f"_rlnBfactorUsedForSharpening {f['BfactorUsedForSharpening']}\n\n"
                        "data_fsc\nloop_\n_rlnAngstromResolution #1\n"
                        "_rlnFourierShellCorrelationCorrected #2\n"
                        "_rlnFourierShellCorrelationUnmaskedMaps #3\n" +
                        "".join(" ".join(map(str, row)) + "\n" for row in rows) + "\n")
                (root / "pp" / arm / (subset + ".star")).write_text(text)
        replay = run("historical_exported_full_sample_curves", None)
        for arm in ("cpu", "default", "allfftw"):
            assert replay["point_estimates"][arm] == historic["point_estimates"][arm], arm
        for arm in ("default", "allfftw"):
            for subset in ("held22", "all24"):
                assert replay["arms"][arm][subset] == historic["arms"][arm][subset], (arm, subset)
        report["historical_full_sample_estimates_match"] = True
    report["result"] = "PASS"
    if args.out:
        with args.out.open("x") as fh:
            json.dump(report, fh, indent=2, sort_keys=True, allow_nan=False)
            fh.write("\n")
    print(f"PASS: {report['mode']}, {len(report['cases'])} analyser subprocesses; descriptive endpoints unchanged")


if __name__ == "__main__":
    main()
