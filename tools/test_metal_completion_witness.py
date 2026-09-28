#!/usr/bin/env python3
"""Check that a dispatch-smoke log cannot masquerade as Metal alignment."""

import tempfile
from pathlib import Path

from run_metal_synthetic_regression import inspect_metal_execution


PROFILE = """[Metal Global Alignment Profile]
Total Metal alignment time: 12.34 ms
"""
COMPLETION = (
    "[Metal Global Alignment Completed] device_id=0 iterations=2 "
    "stages=weights,reference,ccf,ifft,peak,fourier_shift converged=true\n"
)


def inspect(run_text: str, movie_text: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="metal-witness-") as tmp:
        root = Path(tmp)
        run_log = root / "run.log"
        movie_log = root / "movie.log"
        run_log.write_text(run_text)
        movie_log.write_text(movie_text)
        return inspect_metal_execution(run_log, movie_log, 0)


def main() -> None:
    startup = "Using Metal acceleration on device 0 (Apple M4 Pro) for global alignment.\n"
    real = inspect(startup, PROFILE + COMPLETION)
    assert real["complete"], real
    assert real["completed_stages"] == ["ccf", "fourier_shift", "ifft", "peak", "reference", "weights"]

    # This is the historical false-positive pattern: device + profile, with no algorithm stages.
    smoke_stub = inspect(startup, PROFILE)
    assert smoke_stub["profile_marker_found"]
    assert not smoke_stub["completion_marker_found"]
    assert not smoke_stub["complete"]

    wrong_device = inspect(startup, PROFILE + COMPLETION.replace("device_id=0", "device_id=1"))
    assert not wrong_device["completion_marker_found"]
    assert not wrong_device["complete"]

    incomplete_stages = inspect(startup, PROFILE + COMPLETION.replace(",fourier_shift", ""))
    assert not incomplete_stages["completion_marker_found"]
    assert not incomplete_stages["complete"]

    nonconverged = inspect(startup, PROFILE + COMPLETION.replace("converged=true", "converged=false"))
    assert not nonconverged["completion_marker_found"]
    assert not nonconverged["complete"]

    print("PASS: actual all-stage completion accepted; smoke, wrong-device, incomplete, and nonconverged logs rejected")


if __name__ == "__main__":
    main()
