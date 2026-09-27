#!/usr/bin/env python3
"""Same-backend A/B of two MotionCorr builds over a complete movie inventory.

Runs each binary once over the same input STAR with identical options, then
compares every artifact both runs produced. This is a regression comparison
between two builds on one backend. It is not a scientific-equivalence claim and
says nothing about CPU/CUDA agreement or about RELION parity.

Graded strictly:
  .mrc   every pixel, in order, and all 1024 header bytes. The only tolerated
         header difference is RELION's clock stamp in the first label, using
         tools/compare_motioncorr.py's own normalized_mrc_labels -- the repo's
         existing definition, reused, not relaxed.
  .star  field by field via tools/compare_motioncorr.py's compare_star_fields,
         and the per-movie pair is additionally put through the full comparator
         at --gate exact --require-complete-coverage.

Reported with a documented normalization, graded as auxiliary:
  .eps .pdf .log  these embed a wall-clock stamp, the output path, and elapsed
         times. Lines matching those patterns are blanked before comparison;
         the normalization is recorded in the JSON so the reader can see what
         was ignored rather than having to trust a summary.

Controls, each of which must be reported detected:
  missing   an expected output removed from the test tree.
  pixel     one pixel perturbed in a test .mrc.
  header    one non-timestamp header byte perturbed in a test .mrc.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Lines that legitimately differ between two runs of the same code.
NORMALIZE_OUTPUT_ALIASES = []
NORMALIZE_PATTERNS = [
    (r"\d{2}-[A-Za-z]{3}-\d{2}\s+\d{2}:\d{2}:\d{2}", "<TIMESTAMP>"),
    (r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "<TIMESTAMP>"),
    (r"%%CreationDate:.*", "%%CreationDate: <TIMESTAMP>"),
    (r"/CreationDate\s*\([^)]*\)", "/CreationDate (<TIMESTAMP>)"),
    (r"/ModDate\s*\([^)]*\)", "/ModDate (<TIMESTAMP>)"),
    (r"/ID\s*\[[^\]]*\]", "/ID [<ID>]"),
    (r"\b\d+\.\d+\s*(seconds|sec|s)\b", "<ELAPSED>"),
    (r"took\s+[0-9.]+", "took <ELAPSED>"),
    # The CUDA path prints per-kernel wall times in milliseconds into the
    # per-movie log. These are measurements of the machine, not of the result.
    (r"\b\d+\.\d+\s*ms\b", "<ELAPSED_MS>"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_comparator(repo: Path):
    path = repo / "tools" / "compare_motioncorr.py"
    spec = importlib.util.spec_from_file_location("in_tree_comparator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def normalize_text(raw: bytes, root: str) -> str:
    text = raw.decode("utf-8", errors="replace")
    text = text.replace(root, "<OUTPUT_ROOT>")
    for alias in NORMALIZE_OUTPUT_ALIASES:
        text = text.replace(alias, "<OUTPUT_ROOT>")
    for pattern, replacement in NORMALIZE_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


def run_binary(binary: Path, cwd: Path, input_star: str, outdir: Path,
               options: list, threads: int) -> dict:
    cmd = [str(binary), "--i", input_star, "--o", str(outdir),
           *options, "--j", str(threads), "--seed", "1"]
    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    elapsed = time.monotonic() - started
    (outdir.parent / (outdir.name + ".stdout.log")).write_text(proc.stdout)
    (outdir.parent / (outdir.name + ".stderr.log")).write_text(proc.stderr)
    return {
        "command": cmd,
        "cwd": str(cwd),
        "exit_code": proc.returncode,
        "wall_seconds": round(elapsed, 3),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def compare_mrc(module, ref: Path, test: Path) -> dict:
    try:
        ref_header, ref_pixels, ref_raw = module.parse_mrc(ref)
        test_header, test_pixels, test_raw = module.parse_mrc(test)
    except Exception as err:  # a parse failure is a real finding, not a skip
        return {"status": "FAIL", "reason": f"MRC parse failed: {err}"}

    result = module.compare_images(ref_pixels, test_pixels, ref_header,
                                   test_header, ref_raw, test_raw)
    if "error" in result:
        return {"status": "FAIL", "reason": result["error"], "detail": result}

    ok = (result["pixel_identical"]
          and result["core_header_diff_bytes"] == 0
          and result["normalized_label_diff_bytes"] == 0)
    return {
        "status": "PASS" if ok else "FAIL",
        "pixels_compared": result["num_pixels"],
        "pixel_identical": result["pixel_identical"],
        "max_abs_pixel_error": result["max_abs_pixel_error"],
        "core_header_diff_bytes": result["core_header_diff_bytes"],
        "label_header_diff_bytes_raw": result["label_header_diff_bytes"],
        "normalized_label_diff_bytes": result["normalized_label_diff_bytes"],
        "header_normalization": "RELION clock stamp in the first 80-byte MRC "
                                "label, via compare_motioncorr.normalized_mrc_labels",
    }


def compare_star(module, ref: Path, test: Path, ref_root: str, test_root: str) -> dict:
    try:
        ref_star = module.parse_star_file(ref)
        test_star = module.parse_star_file(test)
    except Exception as err:
        return {"status": "FAIL", "reason": f"STAR parse failed: {err}"}
    result = module.compare_star_fields(ref_star, test_star)
    differing = result.get("differences") or []
    identical_text = (normalize_text(ref.read_bytes(), ref_root)
                      == normalize_text(test.read_bytes(), test_root))
    ok = not differing and identical_text
    return {
        "status": "PASS" if ok else "FAIL",
        "field_comparison": result,
        "normalized_text_identical": identical_text,
    }


def compare_auxiliary(ref: Path, test: Path, ref_root: str, test_root: str) -> dict:
    identical_bytes = sha256(ref) == sha256(test)
    ref_text = normalize_text(ref.read_bytes(), ref_root)
    test_text = normalize_text(test.read_bytes(), test_root)
    identical_norm = ref_text == test_text
    result = {
        "status": "PASS" if identical_norm else "FAIL",
        "identical_bytes": identical_bytes,
        "identical_normalized": identical_norm,
        "ref_bytes": ref.stat().st_size,
        "test_bytes": test.stat().st_size,
    }
    if not identical_norm:
        # Show what actually differs rather than asking the reader to accept a
        # verdict. Line pairs only, capped, and only for text-like output.
        ref_lines, test_lines = ref_text.splitlines(), test_text.splitlines()
        samples = [{"line": i + 1, "ref": a[:160], "test": b[:160]}
                   for i, (a, b) in enumerate(zip(ref_lines, test_lines)) if a != b]
        result["differing_line_count"] = (len(samples)
                                          + abs(len(ref_lines) - len(test_lines)))
        result["differing_line_samples"] = samples[:6]
    return result


def inventory(root: Path) -> dict:
    return {str(p.relative_to(root)): p for p in sorted(root.rglob("*")) if p.is_file()}


def compare_trees(module, ref_root: Path, test_root: Path) -> dict:
    ref_files = inventory(ref_root)
    test_files = inventory(test_root)
    all_paths = sorted(set(ref_files) | set(test_files))

    entries = []
    for rel in all_paths:
        entry = {"path": rel}
        if rel not in ref_files:
            entry.update(status="FAIL", reason="present only in reference run's counterpart (missing in reference)")
            entries.append(entry)
            continue
        if rel not in test_files:
            entry.update(status="FAIL", reason="missing in test output tree")
            entries.append(entry)
            continue

        ref, test = ref_files[rel], test_files[rel]
        suffix = ref.suffix.lower()
        entry["ref_sha256"] = sha256(ref)
        entry["test_sha256"] = sha256(test)
        if suffix == ".mrc":
            entry["kind"] = "corrected_image"
            entry.update(compare_mrc(module, ref, test))
        elif suffix == ".star":
            entry["kind"] = "metadata"
            entry.update(compare_star(module, ref, test, str(ref_root), str(test_root)))
        else:
            entry["kind"] = "auxiliary"
            entry.update(compare_auxiliary(ref, test, str(ref_root), str(test_root)))
        entries.append(entry)
    return {"files": entries}


def full_comparator(tool: Path, ref_mrc: Path, test_mrc: Path, ref_star: Path,
                    test_star: Path, json_path: Path) -> dict:
    cmd = [sys.executable, str(tool), "--ref-mrc", str(ref_mrc), "--test-mrc", str(test_mrc),
           "--ref-star", str(ref_star), "--test-star", str(test_star),
           "--gate", "exact", "--require-complete-coverage", "--json-out", str(json_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(json_path.read_text()) if json_path.is_file() else {}
    return {
        "command": cmd,
        "exit_code": proc.returncode,
        "overall_status": data.get("overall_status"),
        "coverage_complete": data.get("coverage", {}).get("complete"),
        "stderr_tail": proc.stderr[-600:],
    }


def controls(module, ref_root: Path, test_root: Path, work: Path) -> dict:
    """Tamper with a copy of the test tree and confirm each defect is caught."""
    mrcs = sorted(test_root.rglob("*.mrc"))
    if not mrcs:
        return {"status": "UNRUN", "reason": "no .mrc in test tree"}
    victim_rel = mrcs[0].relative_to(test_root)
    out = {"victim": str(victim_rel)}

    for label in ("missing", "pixel", "header"):
        clone = work / f"control_{label}"
        if clone.exists():
            shutil.rmtree(clone)
        shutil.copytree(test_root, clone)
        target = clone / victim_rel

        if label == "missing":
            target.unlink()
        elif label == "pixel":
            raw = bytearray(target.read_bytes())
            offset = 1024 + 4 * (len(raw) - 1024) // 8  # a pixel well inside the payload
            raw[offset] ^= 0x01
            target.write_bytes(bytes(raw))
        else:  # header: a core header word, outside the normalized label region
            raw = bytearray(target.read_bytes())
            raw[76] ^= 0x01  # dmin
            target.write_bytes(bytes(raw))

        result = compare_trees(module, ref_root, clone)
        failed = [f for f in result["files"] if f.get("status") == "FAIL"]
        out[label] = {
            "detected": bool(failed),
            "failing_paths": [f["path"] for f in failed][:5],
            "first_reason": (failed[0].get("reason")
                             or failed[0].get("max_abs_pixel_error")
                             or failed[0].get("core_header_diff_bytes")) if failed else None,
        }
        shutil.rmtree(clone)

    out["all_detected"] = all(out[k]["detected"] for k in ("missing", "pixel", "header"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--ref-binary", required=True, type=Path)
    parser.add_argument("--test-binary", required=True, type=Path)
    parser.add_argument("--ref-label", default="main")
    parser.add_argument("--test-label", default="pr")
    parser.add_argument("--tutorial", required=True, type=Path)
    parser.add_argument("--input-star", default="movies.star")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--skip-run", action="store_true",
                        help="reuse output trees already present under --work")
    parser.add_argument("--ref-output-root", default="", help="Original output root embedded in retained hard-linked artifacts")
    parser.add_argument("--test-output-root", default="", help="Original output root embedded in retained hard-linked artifacts")
    args = parser.parse_args()
    NORMALIZE_OUTPUT_ALIASES[:] = [v for v in (args.ref_output_root, args.test_output_root) if v]

    module, tool = load_comparator(args.repo)
    args.work.mkdir(parents=True, exist_ok=True)

    options = ["--use_own", "--dose_weighting", "--dose_per_frame", "1.277",
               "--patch_x", "5", "--patch_y", "5", "--bfactor", "150",
               "--gainref", "Movies/gain.mrc", "--gpu", "0"]

    ref_root = args.work / f"out_{args.ref_label}_j{args.threads}"
    test_root = args.work / f"out_{args.test_label}_j{args.threads}"

    report = {
        "what": f"same-backend regression A/B, {args.ref_label} vs {args.test_label}, CUDA native device 0, j={args.threads}",
        "not_a_claim_about": ["CPU/CUDA agreement", "RELION parity",
                              "scientific equivalence"],
        "comparator": str(tool),
        "comparator_sha256": sha256(tool),
        "options": options + ["--j", str(args.threads), "--seed", "1"],
        "input_star": args.input_star,
        "tutorial": str(args.tutorial),
        "ref_binary": str(args.ref_binary), "ref_binary_sha256": sha256(args.ref_binary),
        "test_binary": str(args.test_binary), "test_binary_sha256": sha256(args.test_binary),
        "normalization_patterns": [p for p, _ in NORMALIZE_PATTERNS],
        "original_output_root_aliases": NORMALIZE_OUTPUT_ALIASES,
    }

    if not args.skip_run:
        for root in (ref_root, test_root):
            if root.exists():
                shutil.rmtree(root)
        report["ref_run"] = run_binary(args.ref_binary, args.tutorial, args.input_star,
                                       ref_root, options, args.threads)
        report["test_run"] = run_binary(args.test_binary, args.tutorial, args.input_star,
                                        test_root, options, args.threads)
        if report["ref_run"]["exit_code"] != 0 or report["test_run"]["exit_code"] != 0:
            report["overall"] = "FAIL"
            report["reason"] = "a run exited nonzero"
            args.json.write_text(json.dumps(report, indent=2) + "\n")
            print("overall: FAIL (run exited nonzero)")
            return 1

    tree = compare_trees(module, ref_root, test_root)
    report["tree_comparison"] = tree

    # Per-movie pair through the unmodified comparator at the exact gate.
    per_movie = []
    for mrc in sorted((ref_root / "Movies").glob("*.mrc")):
        name = mrc.stem
        star = mrc.with_suffix(".star")
        test_mrc = test_root / "Movies" / mrc.name
        test_star = test_root / "Movies" / star.name
        if not (star.is_file() and test_mrc.is_file() and test_star.is_file()):
            per_movie.append({"movie": name, "status": "FAIL",
                              "reason": "incomplete output pair"})
            continue
        out_json = args.work / f"cmp_{args.test_label}_j{args.threads}_{name}.json"
        result = full_comparator(tool, mrc, test_mrc, star, test_star, out_json)
        result["movie"] = name
        result["status"] = ("PASS" if result["overall_status"] == "PASS"
                            and result["coverage_complete"] else "FAIL")
        per_movie.append(result)
    report["per_movie_exact_gate"] = per_movie

    report["controls"] = controls(module, ref_root, test_root, args.work)

    graded = [f for f in tree["files"] if f.get("kind") in ("corrected_image", "metadata")
              or f.get("status") == "FAIL"]
    aux = [f for f in tree["files"] if f.get("kind") == "auxiliary"]
    report["summary"] = {
        "artifacts_total": len(tree["files"]),
        "artifacts_pass": sum(1 for f in tree["files"] if f.get("status") == "PASS"),
        "artifacts_fail": sum(1 for f in tree["files"] if f.get("status") == "FAIL"),
        "corrected_images_compared": sum(1 for f in tree["files"]
                                         if f.get("kind") == "corrected_image"),
        "corrected_images_pass": sum(1 for f in tree["files"]
                                     if f.get("kind") == "corrected_image"
                                     and f.get("status") == "PASS"),
        "total_pixels_compared": sum(f.get("pixels_compared", 0) for f in tree["files"]),
        "star_files_compared": sum(1 for f in tree["files"] if f.get("kind") == "metadata"),
        "auxiliary_compared": len(aux),
        "auxiliary_fail": sum(1 for f in aux if f.get("status") == "FAIL"),
        "per_movie_exact_gate_pass": sum(1 for m in per_movie if m["status"] == "PASS"),
        "per_movie_exact_gate_total": len(per_movie),
        "controls_all_detected": report["controls"].get("all_detected"),
    }

    summary = report["summary"]
    # The scientific products are graded strictly and reported on their own. A
    # difference in an auxiliary log is reported separately with its differing
    # lines attached, so that an unexplained one cannot hide inside a green
    # overall, and an explained one cannot sink a clean result silently either.
    graded_fail = sum(1 for f in tree["files"]
                      if f.get("kind") in ("corrected_image", "metadata")
                      and f.get("status") != "PASS")
    report["overall_graded"] = ("PASS" if graded_fail == 0
                                and summary["total_pixels_compared"] > 0
                                and summary["corrected_images_compared"] == 24
                                and summary["star_files_compared"] == 25
                                and summary["per_movie_exact_gate_total"] == 24
                                and summary["per_movie_exact_gate_pass"] == summary["per_movie_exact_gate_total"]
                                and summary["controls_all_detected"] is True
                                else "FAIL")
    report["overall_auxiliary"] = "PASS" if summary["auxiliary_fail"] == 0 else "FAIL"
    report["overall"] = ("PASS" if report["overall_graded"] == "PASS"
                         and report["overall_auxiliary"] == "PASS" else "FAIL")

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print("overall_graded:", report["overall_graded"],
          "overall_auxiliary:", report["overall_auxiliary"],
          "overall:", report["overall"])
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
