#!/usr/bin/env python3
"""Write provenance.json for the GPU corpus pass (run on 4GPUs).

Usage: collect_provenance.py OUT.json --binary B --source SRC_DIR --kit KITDIR --shared SHARED_DIR
          --inputs INPUT_VERIFY.json --uuid GPU-... --cpus 96-103
Records host/GPU/driver/persistence/THP, the binary hash and linked libraries, the source commit
and cleanliness, the kit and shared-definition file hashes, and the input verification result.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def sh(cmd):
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    return r.stdout.strip()


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--binary', required=True)
    ap.add_argument('--source', required=True)
    ap.add_argument('--kit', required=True)
    ap.add_argument('--shared', required=True)
    ap.add_argument('--inputs', required=True)
    ap.add_argument('--uuid', required=True)
    ap.add_argument('--cpus', default='96-103')
    a = ap.parse_args()
    shared = Path(a.shared)
    rec = {
        'collected_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'host': sh('hostname'),
        'kernel': sh('uname -r'),
        'os': sh('. /etc/os-release; echo $PRETTY_NAME'),
        'cpu_model': sh("grep -m1 'model name' /proc/cpuinfo | cut -d: -f2").strip(),
        'logical_cpus': os.cpu_count(),
        'lane': a.cpus,
        'mem_gib': sh("free -g | awk '/Mem:/{print $2}'"),
        'thp_enabled': sh('cat /sys/kernel/mm/transparent_hugepage/enabled'),
        'thp_defrag': sh('cat /sys/kernel/mm/transparent_hugepage/defrag'),
        'gpu': sh('nvidia-smi --id=%s --query-gpu=index,uuid,name,driver_version,persistence_mode,memory.total,'
                  'pci.bus_id,clocks.max.sm --format=csv,noheader' % a.uuid),
        'nvidia_smi_header': sh('nvidia-smi | sed -n 1,4p'),
        'nvcc': sh('/usr/local/cuda-12.8/bin/nvcc --version | tail -2'),
        'tmpfs_inputs': 'inputs, run directories and products live in /dev/shm (tmpfs): already in RAM, '
                        'like a warm page cache',
        'binary': {'path': a.binary, 'sha256': sha(a.binary), 'bytes': os.path.getsize(a.binary),
                   'ldd': [l.strip() for l in sh('ldd %s' % a.binary).splitlines()
                           if any(k in l for k in ('nvcomp', 'cufft', 'cudart', 'tiff', 'omp', 'fftw'))]},
        'source': {'path': a.source, 'head': sh('git -C %s rev-parse HEAD' % a.source),
                   'status_short': sh('git -C %s status --short | head -5' % a.source),
                   'cmake_build_type': sh('grep CMAKE_BUILD_TYPE: %s/../build-116eb04/CMakeCache.txt' % a.source),
                   'cxx_flags_release': sh('grep "CMAKE_CXX_FLAGS_RELEASE:" %s/../build-116eb04/CMakeCache.txt' % a.source),
                   'use_nvcomp': sh('grep "^USE_NVCOMP" %s/../build-116eb04/CMakeCache.txt' % a.source),
                   'cuda_arch_note': 'built 2026-10-14 from this tree; see build-116eb04.cmake.log'},
        'kit': {'path': a.kit, 'files': {str(p.relative_to(a.kit)): sha(p)
                                          for p in sorted(Path(a.kit).rglob('*.py')) if 'tests' not in p.parts}},
        'shared_definitions': {str(p.relative_to(shared)): sha(p) for p in sorted(shared.rglob('*'))
                               if p.is_file() and '__pycache__' not in p.parts},
        'inputs': json.loads(Path(a.inputs).read_text()),
        'runtime_env': {k: v for k, v in os.environ.items() if k.startswith(('OMP_', 'CUDA_', 'MALLOC_', 'GOMP_'))},
        'logins': sh('who | wc -l'),
    }
    Path(a.out).write_text(json.dumps(rec, indent=1) + '\n')
    print('wrote', a.out)


if __name__ == '__main__':
    main()
