#!/usr/bin/env python3
"""Descriptive endpoint decision frequencies; never scientific certification.

Explicit protocol JSON supplies endpoint directions, margins, critical values and
replication unit. Records bind that file's SHA-256 and declare the complete roster.
No harm truth, bias, false-pass, power or OC acceptance policy is inferred.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from scipy.stats import beta


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load(data):
    return json.loads(data, object_pairs_hook=reject_duplicates,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError(f"nonfinite JSON constant: {value}")))


def finite(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("require finite numeric values (not booleans or strings)")
    return value


def identifier(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("require nonempty string identifiers")
    return value


def fields(value, required, optional=()):
    if (not isinstance(value, dict) or not set(required) <= set(value)
            or not set(value) <= set(required) | set(optional)):
        raise ValueError(f"require fields {required}; optional {optional}")


def bounds(count, total, confidence):
    """Two separately one-sided Clopper-Pearson bounds, NOT a joint confidence interval."""
    alpha = 1 - confidence
    return {"lower_one_sided": 0. if count == 0 else float(beta.ppf(alpha, count, total - count + 1)),
            "upper_one_sided": 1. if count == total else float(beta.ppf(confidence, count + 1, total - count))}


def summarize(protocol_data, records_data, confidence):
    confidence = finite(confidence)
    if not 0 < confidence < 1:
        raise ValueError("explicit confidence must be between zero and one")
    protocol, supplied = load(protocol_data), load(records_data)
    fields(protocol, ("protocol_id", "replication_unit", "endpoints"))
    identifier(protocol["protocol_id"])
    identifier(protocol["replication_unit"])
    if not isinstance(protocol["endpoints"], list) or not protocol["endpoints"]:
        raise ValueError("nonempty endpoint definitions required")
    definitions = {}
    for endpoint in protocol["endpoints"]:
        fields(endpoint, ("endpoint", "direction", "margin", "critical_value"))
        name = identifier(endpoint["endpoint"])
        if name in definitions or endpoint["direction"] not in ("higher", "lower"):
            raise ValueError("duplicate endpoint or invalid direction")
        finite(endpoint["margin"])
        if finite(endpoint["critical_value"]) <= 0:
            raise ValueError("critical value must be positive")
        definitions[name] = endpoint
    fields(supplied, ("protocol_sha256", "replicate_ids", "records"))
    digest = hashlib.sha256(protocol_data).hexdigest()
    if supplied["protocol_sha256"] != digest:
        raise ValueError("frozen protocol SHA-256 mismatch")
    roster = supplied["replicate_ids"]
    if not isinstance(roster, list) or not roster:
        raise ValueError("explicit nonempty replicate roster required")
    for replicate in roster:
        identifier(replicate)
    if len(set(roster)) != len(roster):
        raise ValueError("duplicate replicate in roster")
    if not isinstance(supplied["records"], list):
        raise ValueError("records must be a list")
    computed = {}
    for record in supplied["records"]:
        fields(record, ("replicate_id", "endpoint", "estimate", "se"), ("verdict",))
        key = (identifier(record["replicate_id"]), identifier(record["endpoint"]))
        if key in computed or key[0] not in roster or key[1] not in definitions:
            raise ValueError("duplicate or undeclared replicate/endpoint")
        definition = definitions[key[1]]
        estimate, se = finite(record["estimate"]), finite(record["se"])
        if se < 0:
            raise ValueError("SE must be nonnegative")
        width = definition["critical_value"] * se
        lower, upper = finite(estimate - width), finite(estimate + width)
        margin = definition["margin"]
        if definition["direction"] == "higher":
            verdict = "PASS" if lower >= margin else "FAIL" if upper < margin else "INCONCLUSIVE"
        else:
            verdict = "PASS" if upper <= margin else "FAIL" if lower > margin else "INCONCLUSIVE"
        if "verdict" in record and record["verdict"] != verdict:
            raise ValueError("supplied verdict disagrees with recomputed endpoint decision")
        computed[key] = {**record, "verdict": verdict, "lower_one_sided": lower, "upper_one_sided": upper}
    if set(computed) != {(replicate, endpoint) for replicate in roster for endpoint in definitions}:
        raise ValueError("missing replicate x endpoint records")
    summaries = {}
    for name in sorted(definitions):
        counts = Counter(computed[(replicate, name)]["verdict"] for replicate in roster)
        summaries[name] = {"definition": definitions[name], "n": len(roster),
                           "decisions": {verdict: {"count": counts[verdict],
                               "fraction": counts[verdict] / len(roster),
                               **bounds(counts[verdict], len(roster), confidence)}
                                         for verdict in ("PASS", "FAIL", "INCONCLUSIVE")}}
    return {"schema": "i61-descriptive-oc-v1", "status": "DESCRIPTIVE_ONLY",
            "protocol_id": protocol["protocol_id"], "protocol_sha256": digest,
            "records_sha256": hashlib.sha256(records_data).hexdigest(),
            "replication_unit": protocol["replication_unit"], "replicate_ids": roster,
            "confidence_per_one_sided_bound": confidence,
            "bound_method": "Clopper-Pearson, separately one-sided; no multiplicity adjustment",
            "assumptions": "Binomial bounds assume independent, identically distributed replicates; input records do not verify this.",
            "gate_policy": None, "scientific_verdict": "INCONCLUSIVE",
            "design_truth_status": "UNVALIDATED", "scientific_certification_accepted": False,
            "endpoints": summaries, "recomputed_records": [computed[key] for key in sorted(computed)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--confidence", type=float, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = summarize(args.protocol.read_bytes(), args.records.read_bytes(), args.confidence)
        result["summary_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        with args.out.open("x") as stream:
            json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
    except (OSError, ValueError, TypeError, OverflowError) as error:
        parser.exit(2, f"SUMMARY REFUSED: {error}\n")
    print("DESCRIPTIVE_ONLY: gate policy unset; scientific verdict INCONCLUSIVE")


if __name__ == "__main__":
    main()
