#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Catalogue EMPIAR directories and append verified movies to the S1 manifest.

Existing IDs/recipes are immutable. New movies use the corpus gain, sampling,
dose and EER grouping; their actual header frame count is recorded separately.
Downloads, partials and acquisition records stay under the supplied scratch root.
"""
import argparse
import concurrent.futures
import copy
import ctypes
import ctypes.util
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
import urllib.parse
import urllib.request

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--root", required=True, type=Path)
p.add_argument("--target", type=int, default=10)
p.add_argument("--workers", type=int, default=3)
p.add_argument("--plan-only", action="store_true")
a = p.parse_args()
root = a.root.resolve()
evidence = root / "acquisition"
evidence.mkdir(exist_ok=True)
manifest_path = root / "manifest.json"
manifest = json.loads(manifest_path.read_text())
original_bytes = manifest_path.read_bytes()
if not (evidence / "manifest-before-breadth.json").exists():
    (evidence / "manifest-before-breadth.json").write_bytes(original_bytes)
priority = ["e10216", "e10474f3", "e10641", "e12963", "e10028", "e10361", "e10441", "e10474f4", "e10164"]
catalogues, queues = {}, {}

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()

def save(path, value):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)

for family in priority:
    existing = [r for r in manifest["movies"] if r["family"] == family]
    prototype = existing[0]
    parent = Path(prototype["relative_path"]).parent
    accession, folder = str(parent).split("/", 1)
    url = "https://ftp.ebi.ac.uk/empiar/world_availability/" + accession.removeprefix("EMPIAR-") + "/" + urllib.parse.quote(folder, safe="/") + "/"
    with urllib.request.urlopen(url, timeout=60) as response:
        html = response.read()
    (evidence / (family + "-directory.html.gz")).write_bytes(gzip.compress(html, mtime=0))
    suffix = Path(prototype["relative_path"]).suffix
    names = sorted(set(urllib.parse.unquote(s) for s in re.findall(r'href="([^"?#]+)"', html.decode())
                       if urllib.parse.unquote(s).endswith(suffix) and "/" not in urllib.parse.unquote(s)
                       and "gain" not in s.lower()))
    already = {Path(r["relative_path"]).name for r in existing}
    available = [n for n in names if n not in already]
    need = max(0, a.target - len(existing))
    # Spread deterministic choices across the published directory, retaining the
    # original corpus examples; no outcome-based or size-based selection.
    selected = [available[(k * len(available)) // min(need, len(available))]
                for k in range(min(need, len(available)))]
    catalogues[family] = dict(url=url, directory_html_sha256=hashlib.sha256(html).hexdigest(),
                              listed_movie_count=len(names), existing_count=len(existing),
                              selected=selected, target=a.target)
    queues[family] = [dict(family=family, relative_path=str(parent / n), url=url + urllib.parse.quote(n),
                          prototype=prototype) for n in selected]
    print("catalogue", family, len(names), "selected", len(selected), flush=True)
save(evidence / "catalogues.json", catalogues)
tasks = [queues[f][i] for i in range(max(map(len, queues.values()), default=0)) for f in priority if i < len(queues[f])]
save(evidence / "selection.json", dict(tasks=tasks, selection="evenly spaced sorted directory names excluding existing movies", free_bytes_before=shutil.disk_usage(root).free))
if a.plan_only:
    raise SystemExit(0)

def probe(path, recipe):
    with path.open("rb") as f:
        head = f.read(1024)
    if head[:2] in (b"II", b"MM"):
        t = ctypes.CDLL(ctypes.util.find_library("tiff"))
        t.TIFFOpen.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        t.TIFFOpen.restype = ctypes.c_void_p
        t.TIFFNumberOfDirectories.argtypes = [ctypes.c_void_p]
        t.TIFFNumberOfDirectories.restype = ctypes.c_uint32
        t.TIFFGetField.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        t.TIFFClose.argtypes = [ctypes.c_void_p]
        handle = t.TIFFOpen(str(path).encode(), b"r")
        if not handle:
            raise ValueError("TIFFOpen failed")
        try:
            x, y = ctypes.c_uint32(), ctypes.c_uint32()
            assert t.TIFFGetField(handle, 256, ctypes.byref(x)) == 1
            assert t.TIFFGetField(handle, 257, ctypes.byref(y)) == 1
            n = t.TIFFNumberOfDirectories(handle)
        finally:
            t.TIFFClose(handle)
        groups = recipe.get("eer_grouping", 1)
        info = dict(container="TIFF/EER", nx=x.value, ny=y.value, raw_frames=n,
                    frames=n // groups, grouping=groups, unused_raw_tail=n % groups)
    else:
        nx, ny, nz, mode = struct.unpack_from("<4i", head)
        ns = struct.unpack_from("<i", head, 92)[0]
        expected = 1024 + ns + nx * ny * nz * {0: 1, 1: 2, 2: 4, 6: 2}[mode]
        assert expected == path.stat().st_size, "MRC byte count mismatch"
        info = dict(container="MRC", nx=nx, ny=ny, frames=nz, mode=mode)
    assert sorted((info["nx"], info["ny"])) == sorted((recipe["nx"], recipe["ny"])), "unexpected family geometry"
    assert info["frames"] >= 3, "not a multi-frame alignment movie"
    return info

def fetch(task):
    tag = hashlib.sha256(task["relative_path"].encode()).hexdigest()[:16]
    record_path = evidence / (tag + ".json")
    target = root / "data" / task["relative_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".partial")
    rec = dict(family=task["family"], relative_path=task["relative_path"], url=task["url"],
               free_bytes_before=shutil.disk_usage(root).free, expected_sha256=None,
               started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    try:
        if rec["free_bytes_before"] < 200 * (1 << 30):
            raise RuntimeError("scratch free space below 200 GiB floor")
        if record_path.is_file():
            prior = json.loads(record_path.read_text())
            if prior.get("pass") and target.is_file() and digest(target) == prior["sha256"]:
                return task, prior
        with urllib.request.urlopen(urllib.request.Request(task["url"], method="HEAD"), timeout=60) as response:
            value = response.headers.get("Content-Length")
            rec["expected_bytes"] = int(value) if value else None
            rec["head_headers"] = dict(response.headers)
        cmd = ["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "3", "--connect-timeout", "30",
               "--max-time", "7200", "--speed-limit", "1024", "--speed-time", "120", "--output", str(part), task["url"]]
        rec["argv"] = cmd
        with (evidence / (tag + ".curl.log")).open("w") as log:
            rec["exit_status"] = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode
        assert rec["exit_status"] == 0, "curl failed"
        rec["bytes"] = part.stat().st_size
        assert rec["expected_bytes"] is None or rec["bytes"] == rec["expected_bytes"], "HTTP size mismatch"
        rec["header"] = probe(part, task["prototype"]["recipe"])
        rec["sha256"] = digest(part)
        part.replace(target)
        rec["pass"] = True
        rec["path"] = str(target)
    except Exception as error:
        rec.update({"pass": False, "error": repr(error)})
    save(record_path, rec)
    print(json.dumps({k: rec.get(k) for k in ("family", "relative_path", "pass", "bytes", "error")}), flush=True)
    return task, rec

results = []
with concurrent.futures.ThreadPoolExecutor(a.workers) as pool:
    for task, rec in pool.map(fetch, tasks):
        results.append(rec)
        if not rec["pass"]:
            continue
        # Updates are serial here; original manifest rows/IDs remain unchanged.
        family_rows = [r for r in manifest["movies"] if r["family"] == task["family"]]
        if rec["sha256"] in {r["movie_sha256"] for r in family_rows}:
            rec["duplicate_bytes_not_counted"] = True
            continue
        row = copy.deepcopy(task["prototype"])
        rank = max(r["rank"] for r in family_rows) + 1
        row.update(id=task["family"] + "-%02d" % rank, rank=rank, relative_path=task["relative_path"],
                   movie_source=rec["path"], movie_sha256=rec["sha256"], movie_bytes=rec["bytes"],
                   expected_corpus_sha256=None,
                   acquisition_record=hashlib.sha256(task["relative_path"].encode()).hexdigest()[:16] + ".json",
                   header_probe=rec["header"])
        row["recipe"]["frames"] = rec["header"]["frames"]
        manifest["movies"].append(row)
        save(manifest_path, manifest)
save(evidence / "fetch-summary.json", dict(all_pass=all(r["pass"] for r in results), records=results,
                                           counts={f: sum(r["family"] == f for r in manifest["movies"]) for f in priority}))
raise SystemExit(0 if all(r["pass"] for r in results) else 1)
