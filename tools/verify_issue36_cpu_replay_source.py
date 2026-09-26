#!/usr/bin/env python3
"""Verify the fresh Issue 36 CPU full trace against the frozen source trace."""

import argparse
import hashlib
import json
from pathlib import Path


KEYS = [f"g_i{iteration:02d}_delta{axis}"
        for iteration in (1, 2) for axis in ("x", "y")]
KEYS += ["g_i02_totalx", "g_i02_totaly"]


def sha(path, skip=0):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        source.seek(skip)
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--movie", required=True)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--fresh", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite report")
    frozen_trace, fresh_trace = args.frozen / "trace", args.fresh / "trace"
    if (frozen_trace / "trace_complete").read_text() != "complete\n" or \
            (fresh_trace / "trace_complete").read_text() != "complete\n":
        raise ValueError("Incomplete CPU trace")
    if (frozen_trace / "trace_start").read_bytes() != (fresh_trace / "trace_start").read_bytes():
        raise ValueError("CPU trace movie identity changed")
    arrays = {}
    for key in KEYS:
        old = frozen_trace / f"{key}.bin"
        new = fresh_trace / f"{key}.bin"
        if old.with_suffix(".json").read_bytes() != new.with_suffix(".json").read_bytes():
            raise ValueError(f"CPU trace sidecar changed: {key}")
        old_hash, new_hash = sha(old), sha(new)
        arrays[key] = {"frozen_sha256": old_hash, "fresh_sha256": new_hash,
                       "byte_identical": old_hash == new_hash}
    name = f"20170629_{args.movie}_frameImage.mrc"
    old_image = args.frozen / "output/Movies" / name
    new_image = args.fresh / "output/Movies" / name
    old_payload, new_payload = sha(old_image, 1024), sha(new_image, 1024)
    result = {"movie": args.movie, "array_sha256": arrays,
              "corrected_payload_sha256": {"frozen": old_payload, "fresh": new_payload},
              "all_replay_arrays_identical": all(value["byte_identical"] for value in arrays.values()),
              "corrected_payload_identical": old_payload == new_payload}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    if not result["all_replay_arrays_identical"] or not result["corrected_payload_identical"]:
        raise SystemExit("Fresh CPU source does not match frozen baseline")


if __name__ == "__main__":
    main()
