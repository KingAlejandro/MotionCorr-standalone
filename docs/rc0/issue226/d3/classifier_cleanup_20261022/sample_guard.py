#!/home/alex/.mc-venv/bin/python3
"""Strict GPU3 health/idle guard. Post settling: at most five samples, one second apart.

Every sample is retained and checked for hardware errors before any settling.
No settling on initial/pre samples. Parent holds the canonical GPU3 lock.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

UUID = 'GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d'
phase, prefix = sys.argv[1:]
baseline_path = Path(os.environ['MC_D3_HEALTH_BASELINE'])
# Probe and release the benchmark lock, then recheck hardware/process occupancy.
subprocess.run(['flock', '-n', '/tmp/motioncorr-bench.lock', 'true'], check=True)
for attempt in range(5 if phase == 'post' else 1):
    xml = subprocess.check_output(['nvidia-smi', '-q', '-x', '-i', UUID])
    Path(f'{prefix}-{attempt}.xml').write_bytes(xml)
    gpu = ET.fromstring(xml).find('gpu')
    assert gpu.findtext('uuid') == UUID
    assert gpu.findtext('gpu_recovery_action') == 'None'
    health = {key: ET.tostring(gpu.find(key), encoding='unicode')
              for key in ('ecc_errors', 'retired_pages', 'remapped_rows')}
    # Both corrected and uncorrected volatile/aggregate ECC must be zero here.
    for leaf in gpu.find('ecc_errors').iter():
        if len(leaf) == 0 and leaf.text and leaf.text.strip().isdigit():
            assert int(leaf.text) == 0, f'nonzero ECC: {leaf.tag}={leaf.text}'
    assert gpu.findtext('retired_pages/pending_blacklist') in ('No', 'N/A')
    assert gpu.findtext('retired_pages/pending_retirement') in ('No', 'N/A')
    assert gpu.findtext('remapped_rows/remapped_row_corr') == '0'
    assert gpu.findtext('remapped_rows/remapped_row_unc') == '0'
    assert gpu.findtext('remapped_rows/remapped_row_pending') in ('No', 'N/A')
    assert gpu.findtext('remapped_rows/remapped_row_failure') in ('No', 'N/A')
    if baseline_path.exists():
        assert health == json.loads(baseline_path.read_text()), 'hardware health changed'
    else:
        baseline_path.write_text(json.dumps(health, indent=2) + '\n')
    idle = (not gpu.findall('processes/process_info') and
            gpu.findtext('utilization/gpu_util') == '0 %' and
            int(gpu.findtext('fb_memory_usage/used').split()[0]) <= 2)
    if idle:
        print(f'PASS {phase} GPU3 idle/healthy sample={attempt}', flush=True)
        break
    if phase != 'post' or attempt == 4:
        raise RuntimeError(f'GPU3 not strictly idle: {prefix} sample={attempt}')
    time.sleep(1)
