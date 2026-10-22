#!/usr/bin/env python3
"""Prospective particle-thinning PLAN only; no reconstruction or certification.

Supports the existing Stage-B one-row-per-line data_particles loop, with quoted
tokens. Preserves every byte outside removed particle rows. Multiline values,
multiple particle loops, missing values and ambiguous row identities fail closed.
"""
import argparse
from collections import defaultdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import shlex


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate design JSON key: {key}")
        result[key] = value
    return result


def tokens(line):
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""  # STAR paths are not shell escapes.
    return list(lexer)


def read_particles(data):
    """Parse named columns as in i61_stageB_plan; never import its executing module."""
    lines = data.splitlines(keepends=True)
    text = [line.decode("utf-8") for line in lines]
    blocks = [i for i, line in enumerate(text)
              if re.fullmatch(r"data_particles(?:\s+#.*)?", line.strip())]
    if len(blocks) != 1:
        raise ValueError("require exactly one data_particles block")
    start = blocks[0] + 1
    stop = next((i for i in range(start, len(lines))
                 if text[i].strip().startswith("data_")), len(lines))
    active = [(i, line) for i, line in enumerate(text[start:stop], start)
              if line.strip() and not line.lstrip().startswith("#")]
    if not active or active[0][1].strip() != "loop_":
        raise ValueError("data_particles must start with one loop_")
    columns, rows = [], []
    in_rows = False
    for line_index, line in active[1:]:
        fields = tokens(line)
        if not in_rows and line.lstrip().startswith("_rln"):
            if len(fields) != 1 or fields[0] in columns:
                raise ValueError("invalid or duplicate particle column")
            annotation = line.split("#", 1)
            if len(annotation) == 2 and annotation[1].strip() != str(len(columns) + 1):
                raise ValueError("particle column # indices must be consecutive")
            columns.append(fields[0])
            continue
        in_rows = True
        if (not fields or line.lstrip().startswith(("_", ";", "loop_", "stop_", "save_"))
                or len(fields) != len(columns)):
            raise ValueError(f"unsupported/malformed particle row at line {line_index + 1}")
        if any(value in (".", "?") or not value for value in fields):
            raise ValueError("missing particle values are unsupported")
        rows.append({"line_index": line_index, "values": fields,
                     "row_sha256": sha256(lines[line_index])})
    required = ("_rlnMicrographName", "_rlnRandomSubset", "_rlnImageName")
    if not rows or any(column not in columns for column in required):
        raise ValueError("empty particles or missing movie/half/image columns")
    indices = {name: columns.index(name) for name in required}
    images = set()
    for index, row in enumerate(rows):
        row["index"] = index
        row["movie"] = row["values"][indices["_rlnMicrographName"]]
        row["half"] = row["values"][indices["_rlnRandomSubset"]]
        image = row["values"][indices["_rlnImageName"]]
        if row["half"] not in ("1", "2") or image in images:
            raise ValueError("invalid half assignment or duplicate image identity")
        images.add(image)
    return lines, columns, rows


def subset_bytes(lines, rows, selected):
    removed = {row["line_index"] for row in rows if row["index"] not in selected}
    return b"".join(line for i, line in enumerate(lines) if i not in removed)


def plan(particles, design, out, seed, retain_fraction, project_root,
         reconstruct_program, sym, pad, ctf):
    fraction = Fraction(retain_fraction)
    if not 0 < fraction <= 1 or type(seed) is not int or seed < 0:
        raise ValueError("require 0 < retain fraction <= 1 and a nonnegative integer seed")
    if not sym or not reconstruct_program or not pad > 0:
        raise ValueError("explicit nonempty reconstruction program/symmetry and positive pad required")
    project_root = project_root.resolve(strict=True)
    if not project_root.is_dir():
        raise ValueError("project root must be a directory (particle paths resolve there)")
    # Read each frozen input once; all selections and output hashes bind these snapshots.
    source = particles.read_bytes()
    design_data = design.read_bytes()
    config = json.loads(design_data, object_pairs_hook=unique_object)
    if not isinstance(config, dict) or set(config) != {"particles_sha256", "held_movies"}:
        raise ValueError("design requires exactly particles_sha256 and held_movies")
    if (not isinstance(config["particles_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", config["particles_sha256"])
            or sha256(source) != config["particles_sha256"]):
        raise ValueError("frozen particle input SHA-256 mismatch")
    held = config["held_movies"]
    if (not isinstance(held, list) or len(held) < 2
            or any(not isinstance(m, str) or not m.strip() for m in held)
            or len(set(held)) != len(held)):
        raise ValueError("held_movies requires at least two unique exact micrograph names")
    held = sorted(held)
    lines, columns, rows = read_particles(source)
    strata = defaultdict(list)
    for row in rows:
        if row["movie"] in held:
            strata[(row["movie"], row["half"])].append(row)
    selected, strata_report = set(), []
    for movie in held:
        for half in ("1", "2"):
            group = strata[(movie, half)]
            count = len(group) * fraction.numerator // fraction.denominator
            if not group or not count:
                raise ValueError(f"empty input/retained movie x half stratum: {movie!r}, {half}")

            def rank(row):
                # Versioned SHA ranking avoids Python PRNG/version and traversal-order drift.
                key = ["i61-thinning-v1", seed, movie, half, row["index"], row["row_sha256"]]
                return sha256(json.dumps(key, ensure_ascii=True, separators=(",", ":")).encode())

            chosen = sorted(sorted(group, key=rank)[:count], key=lambda row: row["index"])
            selected.update(row["index"] for row in chosen)
            strata_report.append({"movie": movie, "half": int(half), "input_count": len(group),
                                  "retained_count": count, "actual_retained_fraction": count / len(group),
                                  "selected_rows": [{"index": r["index"], "sha256": r["row_sha256"]}
                                                    for r in chosen]})
    out = out.absolute()
    artifacts, jobs, subsets = {}, [], []
    sets = [("held", None)] + [(f"jk_{i:04d}", movie) for i, movie in enumerate(held)]
    for name, omitted in sets:
        eligible = {r["index"] for r in rows if r["movie"] in held and r["movie"] != omitted}
        baseline = [r for r in rows if r["index"] in eligible]
        half_counts = {h: sum(r["half"] == str(h) for r in baseline) for h in (1, 2)}
        for arm, keep in (("baseline", eligible), ("thinned", eligible & selected)):
            relative = f"stars/{arm}/{name}.star"
            data = subset_bytes(lines, rows, keep)
            artifacts[relative] = data
            chosen = [r for r in rows if r["index"] in keep]
            subsets.append({"arm": arm, "subset": name, "omitted_movie": omitted,
                            "star": relative, "sha256": sha256(data), "count": len(keep),
                            "selected_rows_sha256": sha256(json_bytes([
                                {"index": r["index"], "sha256": r["row_sha256"]} for r in chosen])),
                            "per_half": {str(h): {"baseline_count": half_counts[h],
                                "retained_count": sum(r["half"] == str(h) for r in chosen),
                                "actual_retained_fraction": sum(r["half"] == str(h) for r in chosen) / half_counts[h]}
                                         for h in (1, 2)}})
            for half in (1, 2):
                output = f"rec/{arm}/{name}_half{half}_class001_unfil.mrc"
                argv = [reconstruct_program, "--i", str(out / relative), "--o", str(out / output),
                        "--sym", sym, "--subset", str(half), "--pad", str(pad)]
                if ctf:
                    argv.append("--ctf")
                jobs.append({"status": "UNRUN", "arm": arm, "subset": name,
                             "omitted_movie": omitted, "half": half, "cwd": str(project_root),
                             "argv": argv, "input_star_sha256": sha256(data), "output": output,
                             "log": f"logs/{arm}_{name}_half{half}.log"})
    manifest = {"schema": "i61-thinning-plan-v1", "status": "PLAN_ONLY",
                "design_truth_status": "UNVALIDATED", "scientific_certification_accepted": False,
                "gate_policy": None, "scientific_verdict": "INCONCLUSIVE",
                "warning": "Particle fraction is not exact SSNR rho or accepted harm truth.",
                "inputs": {"particles": {"path": str(particles.resolve()), "sha256": sha256(source),
                                          "count": len(rows)},
                           "design": {"path": str(design.resolve()), "sha256": sha256(design_data)}},
                "planner_sha256": sha256(Path(__file__).read_bytes()),
                "selection": {"algorithm": "sha256-rank-v1", "seed": seed,
                              "requested_fraction": str(fraction), "rounding": "floor per movie x half",
                              "held_movies": held, "columns": columns, "strata": strata_report},
                "subsets": subsets, "job_count": len(jobs),
                "jobs_sha256": sha256(json_bytes(jobs))}
    # Validate everything before creating a new destination. An interrupted publication
    # deliberately leaves evidence in place and cannot be resumed by overwriting it.
    out.mkdir(parents=False, exist_ok=False)
    for arm in ("baseline", "thinned"):
        (out / "rec" / arm).mkdir(parents=True)
    (out / "logs").mkdir()
    for relative, data in {**artifacts, "jobs.json": json_bytes(jobs),
                           "manifest.json": json_bytes(manifest)}.items():
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("particles", "design", "out", "project-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--retain-fraction", required=True)
    parser.add_argument("--reconstruct-program", required=True)
    parser.add_argument("--sym", required=True)
    parser.add_argument("--pad", type=int, required=True)
    parser.add_argument("--ctf", choices=("yes", "no"), required=True)
    args = vars(parser.parse_args())
    args["ctf"] = args["ctf"] == "yes"
    try:
        manifest = plan(**args)
    except (OSError, ValueError, TypeError, ArithmeticError) as error:
        parser.exit(2, f"PLAN REFUSED: {error}\n")
    print(f"PLAN_ONLY: {manifest['job_count']} UNRUN jobs; truth UNVALIDATED; INCONCLUSIVE")


if __name__ == "__main__":
    main()
