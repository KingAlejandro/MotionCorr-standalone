"""Shared, fail-closed venue checks for the prepared cpu64 measurement drivers."""
import os
import socket


def add_arguments(parser):
    parser.add_argument("--expected-host", default="small-refmac-machine",
                        help="Exact socket hostname required before any workload or output creation")
    parser.add_argument("--cpus-j1", required=True, help="Explicit Linux CPU list containing exactly one allowed CPU")
    parser.add_argument("--cpus-j4", required=True, help="Explicit Linux CPU list containing exactly four allowed CPUs")


def cpu_list(text, count):
    cpus = []
    for item in text.split(","):
        if not item or item.strip() != item:
            raise ValueError("CPU lists must contain nonempty, unpadded entries")
        fields = item.split("-")
        if len(fields) not in (1, 2) or any(not field.isascii() or not field.isdigit() for field in fields):
            raise ValueError("Expected CPU indices or increasing ranges, for example 8,10-12")
        first, last = int(fields[0]), int(fields[-1])
        if last < first or last - first > 65536:
            raise ValueError("CPU range is reversed or excessive")
        cpus.extend(range(first, last + 1))
    if len(cpus) != len(set(cpus)):
        raise ValueError("CPU list contains repeated indices")
    if len(cpus) != count:
        raise ValueError(f"Expected exactly {count} CPU(s), received {len(cpus)}")
    return sorted(cpus)


def validate(args):
    actual = socket.gethostname()
    if not args.expected_host or actual != args.expected_host:
        raise RuntimeError(f"Wrong timing venue: hostname {actual!r}, expected exactly {args.expected_host!r}; no workload started")
    if not hasattr(os, "sched_getaffinity"):
        raise RuntimeError("Linux CPU affinity support is required; no workload started")
    allowed = sorted(os.sched_getaffinity(0))
    requested = {1: cpu_list(args.cpus_j1, 1), 4: cpu_list(args.cpus_j4, 4)}
    for threads, cpus in requested.items():
        if not set(cpus).issubset(allowed):
            raise RuntimeError(f"j{threads} CPU list {cpus} is outside allowed affinity {allowed}; no workload started")
    return {"expected_host": args.expected_host, "actual_host": actual,
            "allowed_affinity": allowed, "requested_affinity": requested,
            "masks": {threads: ",".join(map(str, cpus)) for threads, cpus in requested.items()},
            "scope": "Hostname and allowed CPU lists verified; this does not certify host-wide workload isolation"}
