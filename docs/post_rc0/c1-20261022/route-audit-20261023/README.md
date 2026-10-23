# Retrospective C1 nvCOMP route audit, 23 October 2026

**PASS, bounded route witness:** both C1 tutorial arms already ran in iteration 3.
Each has 24 distinct tutorial TIFFs witnessed as `nvcomp`, using tested source
`e77a51a220cb0d91f4ac3c7fac211876d0c6833f` and binary
`d7c4e2e3baa370defb5d3252cd0ca6e4d7ab57c9a1665037fa54d461a51b2e6d`.
G started at 21:24:14Z and L at 21:25:26Z on 22 October, GPU3
`GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`, CPUs 8–9, OMP 2.
Both native exits and pre/post health checks were 0, and cleanup had no remaining
members. This corrects the earlier summary's claim that no C1 arm had run.
The original receipts, archives and failed iterations are unchanged.

The parent performed only a read-only file/hash audit at 00:17:47Z on 23 October,
4-gpu-vm CPU 13. No native process, build, GPU query or GPU job was launched.
`readback_remote.py` is the exact executed script; `readback.json` is its output.
The script is distributed under the repository's GPL-2.0-or-later licence.

```
ssh -J ccp4-gateway -oBatchMode=yes -oConnectTimeout=10 -oConnectionAttempts=1 4GPUs \
  'taskset -c 13 python3 -I -B -' < readback_remote.py > readback.json
/Users/alex.konstantinov/.local/bin/python3 -I -B verify_routes.py > VERIFICATION.json
```

`verify_routes.py` reproduces the verification locally without network or compute
jobs: the two live RUN hashes and parsed objects equal the already-retained
`evidence/c1-evidence-iteration3.tgz` members; receipt and live binary hashes equal
the retained build receipt; the source comes from the qualification manifest.
It checks exact input-STAR hash, the pinned two-column 24-movie input inventory,
and the complete ordered witness inventory against both the original witness
files and the RUN records. It also checks CPU/OMP settings, UUID, PID route
witness, health receipts and empty post-run process census. `VERIFICATION.json`
binds those consumed artifacts and the verifier by SHA-256.

This is a parent evidence reconciliation, not a fresh independent review or new
native qualification. It establishes W1's named tutorial route row only. It does
not complete CUDA L product attribution, TIFF identity-change controls, poisoned
nvCOMP ingestion, dataset/recovery rows, science, cost, multi-device execution or
C1 acceptance. The user-requested GPU pause remains in force.
