#!/usr/bin/env python3
"""Freeze the qualification manifest: source SHA, tool hashes, row list. usage: make_manifest.py SOURCE_SHA OUT.json"""
import hashlib, json, subprocess, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sha = sys.argv[1]
tools = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((here / 'tools').iterdir()) if p.is_file()}
plan = hashlib.sha256((here / 'QUALIFICATION_PLAN.md').read_bytes()).hexdigest()
m = {'schema': 'c1-qualification-manifest/1', 'source_sha': sha, 'base_main': '3691374061f782bc84531fd1c79d017ddcb5a7c2',
     'lane': {'host': '4GPUs', 'gpu_uuid': 'GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d', 'cpus': '8-9', 'compile_parallel': 2},
     'plan_sha256': plan, 'tools_sha256': tools,
     'rows': ['I1', 'H1', 'B1', 'E1', 'C1-cpu', 'C1-cuda', 'C1-nvcomp', 'F1', 'S1', 'T24', 'K267', 'K269', 'K272', 'R12', 'R9', 'A13', 'W1'],
     'unrun_by_design': ['multi-GPU 1/2/4 arms', 'run_dataset endpoint', 'QF items 5,6,7,11,15', 'SCARF', 'performance', 'downstream science']}
Path(sys.argv[2]).write_text(json.dumps(m, indent=1) + '\n')
