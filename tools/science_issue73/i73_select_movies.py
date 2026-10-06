#!/usr/bin/env python3
"""Draw the Issue #73 confirmatory movie sample, reproducibly.

The draw depends only on the deposited EMPIAR-12963 particle metadata and a
fixed seed, so anyone can re-derive the identical movie list without access to
any arm's output.  Run it before acquiring movies, not after.

Usage:
    python3 tools/science_issue73/i73_select_movies.py \
        --passthrough J189_passthrough_particles.cs [--n 350] [--seed 73]

Prints the selected movie basenames, one per line, plus a JSON summary on
stderr.  The two development movies named in PROTOCOL.md §4 are always
excluded.
"""

import argparse
import json
import re
import sys
from collections import Counter

import numpy as np

# Development movies (PROTOCOL.md section 4): excluded from the confirmatory draw.
DEV_MOVIES = (
    "FoilHole_4677724_Data_4659374_4659376_20230406_041554_EER",
    "FoilHole_4681533_Data_4659374_4659376_20230406_062633_EER",
)

BASENAME = re.compile(r".*?_(FoilHole_.*?_EER)_patch_aligned.*")


def movie_basenames(passthrough_path: str) -> list:
    """Map every particle to the basename of the EER movie it came from."""
    t = np.load(passthrough_path, allow_pickle=False)
    paths = (x.decode() for x in t["location/micrograph_path"])
    return [BASENAME.sub(r"\1", p) for p in paths]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--passthrough", required=True,
                    help="J189_passthrough_particles.cs from EMPIAR-12963")
    ap.add_argument("--n", type=int, default=350, help="movies to draw")
    ap.add_argument("--seed", type=int, default=73, help="frozen draw seed")
    args = ap.parse_args()

    counts = Counter(movie_basenames(args.passthrough))
    for dev in DEV_MOVIES:
        counts.pop(dev, None)

    # Sort by basename so the population order is canonical and independent of
    # dict iteration order, then draw without replacement.
    population = sorted(counts)
    if args.n > len(population):
        sys.exit(f"requested {args.n} movies but only {len(population)} available")

    rng = np.random.default_rng(args.seed)
    picked = sorted(rng.choice(len(population), size=args.n, replace=False).tolist())
    selected = [population[i] for i in picked]

    for name in selected:
        print(name)

    summary = {
        "seed": args.seed,
        "n_requested": args.n,
        "population_size": len(population),
        "excluded_development_movies": list(DEV_MOVIES),
        "expected_particles": sum(counts[m] for m in selected),
        "particles_min": min(counts[m] for m in selected),
        "particles_median": int(np.median([counts[m] for m in selected])),
        "particles_max": max(counts[m] for m in selected),
    }
    print(json.dumps(summary, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
