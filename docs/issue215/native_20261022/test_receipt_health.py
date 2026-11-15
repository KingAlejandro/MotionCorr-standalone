#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reproduce driver-570 XML handling and reject missing/error health data."""
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from run_native import parse_health

source = Path(__file__).resolve().parent / "attempt01/pre-xml.log"
parse_health(source)
rejected = 0
with tempfile.TemporaryDirectory() as tmp:
    target = Path(tmp) / "health.xml"
    for field, value in (
        ("ecc_errors/volatile/dram_uncorrectable", "1"),
        ("ecc_errors/volatile/sram_uncorrectable_parity", "1"),
        ("ecc_errors/volatile/sram_uncorrectable_secded", "1"),
        ("ecc_errors/volatile/dram_uncorrectable", None),
        ("gpu_recovery_action", "Reset"),
        ("gpu_recovery_action", None),
        ("retired_pages/pending_blacklist", "Yes"),
        ("remapped_rows/remapped_row_pending", "Yes"),
        ("remapped_rows/remapped_row_failure", "Yes"),
        ("uuid", "wrong GPU"),
    ):
        tree = ET.parse(source)
        tree.getroot().find("gpu/" + field).text = value
        tree.write(target)
        try:
            parse_health(target)
        except AssertionError:
            rejected += 1
        else:
            raise RuntimeError("accepted invalid health: " + field)
assert rejected == 10
print("PASS: retained driver-570 XML accepted; 10 hardware/missing-data/UUID controls rejected")
