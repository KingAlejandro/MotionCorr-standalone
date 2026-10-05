#!/usr/bin/env python3
"""Real mid-run source mutation must fail one movie in either writer mode.
SPDX-License-Identifier: GPL-2.0-or-later. Only private synthetic inputs are changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
import tempfile
from test_resume_processing_identity import fixture, write_star, command, require
from test_hotpixel_rng_determinism import read_mrc_pixels
from test_gain_cache import write_mrc


def run_case(original_binary, shim, work, kind):
    work.mkdir(parents=True, exist_ok=True)
    fixture(work)
    binary = work / "motioncorr-private"
    shutil.copy2(original_binary, binary)
    options = {}
    source = work / "a.mrc"
    if kind == "gain":
        source = work / "gain.mrc"
        write_mrc(source, [[1.0] * (96 * 96)], nx=96, ny=96)
        options["--gainref"] = source.name
    elif kind == "defect":
        source = work / "defect.txt"
        source.write_text("8 8 1 1\n")
        options["--defect_file"] = source.name
    elif kind == "executable":
        source = binary
    write_star(work / 'single.star', ['a.mrc'])
    write_star(work / 'movies.star', ['a.mrc', 'b.mrc'])
    records = []
    for sync in (False, True):
        out = work / ('sync' if sync else 'async')
        result = subprocess.run(command(binary, out, {**options, '--sync_output': sync}, 'single.star'), cwd=work,
                                capture_output=True, text=True, timeout=60)
        require(result.returncode == 0, 'initial healthy seed failed: ' + result.stderr)
        old_marker = (out / 'a.star').read_bytes()
        old_joint = (out / 'corrected_micrographs.star').read_bytes()
        original = source.read_bytes()
        before_stat = source.stat()
        original_sha = hashlib.sha256(original).hexdigest()
        replacement = work / 'executable-replacement'
        if kind == 'executable': shutil.copy2(binary, replacement)
        witness = work / ('mutation-' + str(sync) + '.log')
        env = dict(os.environ)
        env['DYLD_INSERT_LIBRARIES' if sys.platform == 'darwin' else 'LD_PRELOAD'] = str(shim)
        env.update(MC_RECEIPT_MUTATE_AFTER_CLOSE=str(out / 'a.mrc'),
                   MC_RECEIPT_MUTATE_INPUT=str(source), MC_RECEIPT_MUTATION_WITNESS=str(witness),
                   MC_RECEIPT_MUTATION_KIND=kind, MC_RECEIPT_REPLACEMENT=str(replacement))
        argv = command(binary, out, {**options, '--sync_output': sync})
        result = subprocess.run(argv, cwd=work, env=env, capture_output=True, text=True, timeout=60)
        (work / ('mutation-' + str(sync) + '.stdout')).write_text(result.stdout)
        (work / ('mutation-' + str(sync) + '.stderr')).write_text(result.stderr)
        require(witness.exists(), 'mutation seam absent, exit=' + str(result.returncode) + ': ' + result.stderr)
        require(witness.read_text() == 'ACTUAL_SOURCE_CHANGED_AFTER_IMAGE_CLOSE\n', 'mutation seam not reached exactly once')
        require(source.stat().st_ino != before_stat.st_ino if kind == 'executable' else source.read_bytes() != original,
                'source content/identity did not actually change')
        named_source = str(source) if kind == 'executable' else source.name
        changed_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        changed_inode = source.stat().st_ino
        require(result.returncode > 0 and 'a.mrc' in result.stderr and
                'changed since processing snapshot' in result.stderr and named_source in result.stderr,
                'mid-run change did not fail named movie')
        require(not (out / 'a.star').exists() and bool(old_marker), 'old completion marker survived observed source change')
        require((out / 'corrected_micrographs.star').read_bytes() == old_joint, 'source-change failure published joint success')
        if kind == 'input':
            require((out / 'b.mrc').is_file() and (out / 'b.star').is_file(),
                    'healthy remaining movie was aborted by writer mode')
        else:
            # Shared gain/defect/executable snapshots apply to B too. Continue
            # to its named refusal rather than silently certifying changed inputs.
            require('Movie b.mrc:' in result.stderr and
                    'failed for 2 movie(s): a.mrc b.mrc' in result.stderr and not (out / 'b.star').exists(),
                    'global source change aborted instead of reporting both movie failures')
        if kind != 'executable': source.write_bytes(original)
        if kind == 'input':
            reference = work / ('healthy-' + str(sync))
            write_star(work / 'b.star', ['b.mrc'])
            healthy = subprocess.run(command(binary, reference, {**options, '--sync_output': sync}, 'b.star'), cwd=work,
                                     capture_output=True, text=True, timeout=60)
            require(healthy.returncode == 0 and read_mrc_pixels(out / 'b.mrc') == read_mrc_pixels(reference / 'b.mrc'),
                    'remaining healthy movie pixels differ from standalone same-backend processing')
        records.append({'source': kind, 'sync': sync, 'command': argv, 'exit': result.returncode,
                        'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                        'shim_sha256': hashlib.sha256(shim.read_bytes()).hexdigest(),
                        'source_before_sha256': original_sha, 'source_after_sha256': changed_sha,
                        'source_before_inode': before_stat.st_ino, 'source_after_inode': changed_inode,
                        'actual_source_changed': True, 'completion_invalidated': True,
                        'healthy_remaining_movie': kind == 'input', 'global_source_both_named': kind != 'input', 'joint_unchanged': True})
    return records


def run(binary, shim, work, cases=None):
    records = []
    for kind in cases or ('input', 'gain', 'defect', 'executable'):
        records.extend(run_case(binary, shim, work / kind, kind))
    (work / 'summary.json').write_text(json.dumps(records, indent=2) + '\n')
    print('PASS actual two-movie source mutation sync/async continuation, invalidation and joint withholding')
    print(json.dumps(records))


def main():
    p = argparse.ArgumentParser(); p.add_argument('--binary', type=Path, required=True); p.add_argument('--shim', type=Path, required=True)
    p.add_argument('--work', type=Path); p.add_argument('--case', choices=['input', 'gain', 'defect', 'executable'])
    a = p.parse_args()
    if a.work:
        a.work.mkdir(parents=True, exist_ok=True)
        run(a.binary.resolve(), a.shim.resolve(), a.work.resolve(), [a.case] if a.case else None)
        return
    with tempfile.TemporaryDirectory(prefix='receipt-source-mutation-') as directory:
        run(a.binary.resolve(), a.shim.resolve(), Path(directory).resolve(), [a.case] if a.case else None)


if __name__ == '__main__': main()
