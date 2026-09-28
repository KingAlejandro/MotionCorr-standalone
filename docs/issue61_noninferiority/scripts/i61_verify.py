#!/usr/bin/env python3
"""Issue 61: verify that the matched design is actually matched.

Replaces the positional-column shell check that shipped in PR #65, which review finding
r4119264419 showed hashed only seven columns by position and silently omitted
`_rlnAnglePsi`, and finding r4119264433 showed covered only five of the six arms.

The invariant under test is strong and stated positively:

  * every declared metadata field must be PRESENT in every arm (a renamed or dropped
    column must fail, not pass by being absent from both sides);
  * every declared metadata field must be byte-identical across arms;
  * the whole `data_particles` block must be byte-identical across arms, so a field this
    script forgot to name cannot differ unnoticed either;
  * every extracted particle stack must DIFFER between arms, for every movie, because
    otherwise the arms are not distinct data and the comparison is vacuous.

Usage: i61_verify.py <project-root> <arm> [<arm> ...]
       expects <project-root>/proj/<arm>/Extract61/{particles.star,Movies/*.mrcs}
"""
import hashlib, json, os, sys

# Fields whose equality across arms IS the matched-orientation premise.
REQUIRED = [
    "_rlnCoordinateX", "_rlnCoordinateY",                       # selection
    "_rlnAngleRot", "_rlnAngleTilt", "_rlnAnglePsi",            # orientation (all three)
    "_rlnOriginXAngst", "_rlnOriginYAngst",                     # origin (both)
    "_rlnRandomSubset",                                         # half-set membership
    "_rlnMicrographName", "_rlnImageName", "_rlnOpticsGroup", "_rlnGroupNumber",
    "_rlnDefocusU", "_rlnDefocusV", "_rlnDefocusAngle",         # CTF held common
    "_rlnCtfBfactor", "_rlnCtfScalefactor", "_rlnPhaseShift",
]


def read_particles(path):
    """Return (column-name -> index, rows) for the data_particles loop."""
    lines = open(path).read().splitlines()
    i = lines.index("data_particles")
    j = i
    while not lines[j].strip().startswith("loop_"):
        j += 1
    k = j + 1
    cols = []
    while lines[k].strip().startswith("_rln"):
        cols.append(lines[k].strip().split()[0])
        k += 1
    rows = [l.split() for l in lines[k:] if l.strip()]
    return {c: n for n, c in enumerate(cols)}, rows


def digest(parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode())
        h.update(b"\x1f")
    return h.hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            c = fh.read(1 << 22)
            if not c:
                break
            h.update(c)
    return h.hexdigest()


def main(root, arms):
    report = {"root": root, "arms": arms, "required_fields": REQUIRED,
              "field_digests": {}, "block_digest": {}, "stack_digests": {},
              "missing_fields": {}, "n_particles": {}}
    failures = []

    for arm in arms:
        star = f"{root}/proj/{arm}/Extract61/particles.star"
        idx, rows = read_particles(star)
        missing = [f for f in REQUIRED if f not in idx]
        report["missing_fields"][arm] = missing
        report["n_particles"][arm] = len(rows)
        if missing:
            failures.append(f"{arm}: required field(s) absent from the STAR: {missing}")
            continue
        report["field_digests"][arm] = {f: digest([r[idx[f]] for r in rows]) for f in REQUIRED}
        report["block_digest"][arm] = digest([" ".join(r) for r in rows])

    # 1. every required field identical across arms
    for f in REQUIRED:
        vals = {report["field_digests"][a][f] for a in arms if a in report["field_digests"]}
        if len(vals) != 1:
            failures.append(f"field {f} DIFFERS across arms ({len(vals)} distinct digests)")
    # 2. whole particle block identical across arms
    blocks = set(report["block_digest"].values())
    if len(blocks) != 1:
        failures.append(f"data_particles block differs across arms ({len(blocks)} distinct digests)")
    # 3. particle counts identical
    counts = set(report["n_particles"].values())
    if len(counts) != 1:
        failures.append(f"particle counts differ across arms: {report['n_particles']}")

    # 4. every stack must differ between arms, for every movie
    movies = sorted(os.path.basename(p) for p in
                    os.listdir(f"{root}/proj/{arms[0]}/Extract61/Movies") if p.endswith(".mrcs"))
    for m in movies:
        per = {}
        for arm in arms:
            p = f"{root}/proj/{arm}/Extract61/Movies/{m}"
            per[arm] = file_digest(p) if os.path.exists(p) else None
        report["stack_digests"][m] = per
        present = [v for v in per.values() if v]
        if len(present) != len(arms):
            failures.append(f"stack {m}: missing for {[a for a in arms if not per[a]]}")
        elif len(set(present)) != len(present):
            dup = [a for a in arms for b in arms if a < b and per[a] == per[b]]
            failures.append(f"stack {m}: identical pixels between arms {dup}")

    report["n_movies_checked"] = len(movies)
    report["n_stacks_checked"] = len(movies) * len(arms)
    report["failures"] = failures
    report["verdict"] = "MATCHED_DESIGN_VERIFIED" if not failures else "MATCHED_DESIGN_FAILED"

    out = f"{root}/results/matched_design_verification.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(report, open(out, "w"), indent=1, sort_keys=True)

    print(f"arms checked            : {len(arms)}  {arms}")
    print(f"required fields         : {len(REQUIRED)} (all present in every arm: "
          f"{all(not v for v in report['missing_fields'].values())})")
    print(f"particles per arm       : {sorted(counts)}")
    print(f"shared field digests    : {len(set(tuple(sorted(report['field_digests'][a].items())) for a in arms))}"
          f" distinct field-digest sets across arms (want 1)")
    print(f"shared block digest     : {sorted(blocks)[0][:16]} ({len(blocks)} distinct, want 1)")
    print(f"stacks checked          : {report['n_stacks_checked']} "
          f"({len(movies)} movies x {len(arms)} arms), all distinct per movie: "
          f"{not any('identical pixels' in f for f in failures)}")
    print(f"VERDICT                 : {report['verdict']}")
    for f in failures:
        print("  FAILURE:", f)
    return 0 if not failures else 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2:]))
