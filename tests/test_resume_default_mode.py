#!/usr/bin/env python3
"""Actual no-receipt default versus explicit/implied strict descriptor-read faults.
SPDX-License-Identifier: GPL-2.0-or-later. Faults target only private fixtures.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import shutil
import re
import struct
import tempfile
import test_resume_processing_identity as t
from test_gain_cache import write_mrc


def image_fingerprint(path):
    data = path.read_bytes()
    t.require(len(data) >= 1024, 'short MRC header')
    nx, ny, nz, mode = struct.unpack_from('<4i', data)
    nsymbt = struct.unpack_from('<i', data, 92)[0]
    t.require(mode == 2 and min(nx, ny, nz) > 0 and nsymbt >= 0 and
              len(data) == 1024 + nsymbt + nx * ny * nz * 4, 'unexpected full MRC extent')
    labels = bytearray(data[224:1024])
    timestamp = rb"\b\d{2}-[A-Za-z]{3}-\d{2}\s+\d{2}:\d{2}:\d{2}\b"
    labels[:80] = re.sub(timestamp, lambda match: b'0' * len(match.group()), bytes(labels[:80]))
    # Every nonvolatile label, all 1024 header bytes, extended header and
    # complete pixel payload survive; only writer clock text is normalized.
    return data[:224] + bytes(labels) + data[1024:]


def images(out):
    return {p.name: image_fingerprint(p) for p in out.glob('a*.mrc')}


def run(binary, shim, work, old=False, mutation_shim=None):
    checks_before = t.CHECKS
    work.mkdir(parents=True, exist_ok=True)
    t.fixture(work)
    gain = work / 'gain.mrc'
    write_mrc(gain, [[1.0] * (96 * 96)], nx=96, ny=96)
    normal = {'--write_resume_receipts': False, '--gainref': str(gain)}
    reference = work / 'reference'
    if not old:
        t.healthy(binary, work, reference, normal)
        t.require('data_motioncorr_processing' not in (reference / 'a.star').read_text(), 'ordinary default wrote a receipt')
    for kind, source in [('executable', binary), ('gain', gain), ('movie', work / 'a.mrc')]:
        witness = work / (kind + '.witness')
        env = dict(os.environ)
        env['DYLD_INSERT_LIBRARIES' if sys.platform == 'darwin' else 'LD_PRELOAD'] = str(shim)
        env.update(MC_RECEIPT_READ_FAULT_PATH=str(source), MC_RECEIPT_READ_FAULT_WITNESS=str(witness))
        out = work / ('ordinary-' + kind)
        result = subprocess.run(t.command(binary, out, normal), cwd=work, env=env, capture_output=True, text=True, timeout=60)
        if old:
            t.require(result.returncode > 0 and witness.is_file() and 'read:' in result.stderr,
                      'predecessor did not reach actual unwanted default digest read: ' + result.stderr)
            t.require('write_resume_receipts' not in result.stderr, 'unknown option is not a powered predecessor control')
            continue
        t.require(result.returncode == 0 and not witness.exists(), 'ordinary default entered digest read path: ' + result.stderr)
        t.require('data_motioncorr_processing' not in (out / 'a.star').read_text(), 'ordinary fault arm wrote receipt')
        t.require(images(out) == images(reference), 'no-hash default changed full normalized MRC headers/pixels')
        t.require((out / 'a.star').read_bytes() == (reference / 'a.star').read_bytes(), 'ordinary default changed saved model')
        # Fresh opt-in and strict resume in a fresh directory must both enter
        # actual digest reads. These are EIO witnesses, not parser exit checks.
        for name, mode in [('explicit', {'--write_resume_receipts': True}),
                           ('implied', {'--only_do_unfinished': True})]:
            strict = work / (name + '-' + kind)
            result = subprocess.run(t.command(binary, strict, {**normal, **mode}), cwd=work, env=env, capture_output=True, text=True, timeout=60)
            t.require(result.returncode > 0 and witness.is_file() and 'read:' in result.stderr,
                      name + ' strict mode bypassed actual digest failure: ' + result.stderr)
            t.require(not (strict / 'a.star').exists() and not (strict / 'corrected_micrographs.star').exists(),
                      'digest failure published completion')
            witness.unlink()
    if old:
        print('PASS predecessor actual default digest reads: executable/gain/movie; no new flag passed')
        return t.CHECKS - checks_before
    adapter = work / 'fake-motioncor2'
    adapter.write_text('#!/bin/sh\ntouch ADAPTER_EXECUTED\nexit 0\n'); adapter.chmod(0o755)
    external = t.invoke(binary, work, work / 'external', {'--use_own': False, '--use_motioncor2': True,
                        '--motioncor2_exe': str(adapter), '--gainref': str(gain), '--gain_rot': '1'})
    t.require(external.returncode > 0 and '--write_resume_receipts requires --use_own' in external.stderr,
              'external receipt opt-in was not refused')
    t.require(not (work / 'ADAPTER_EXECUTED').exists() and not (work / 'external/gain.mrc').exists(),
              'external receipt refusal ran adapter or mutated gain')
    # Ordinary fresh reprocessing must remove a previous receipt rather than
    # leave a stale strict completion marker attached to new numerical products.
    replacement = work / 'replacement'
    t.healthy(binary, work, replacement, {'--gainref': str(gain)})
    t.require('data_motioncorr_processing' in (replacement / 'a.star').read_text(), 'explicit receipt seed absent')
    t.require(images(replacement) == images(reference), 'explicit receipts changed complete MRC headers/pixels')
    t.require((replacement / 'a.star').read_text().split('\n# version 50001\n\ndata_motioncorr_processing', 1)[0].rstrip() ==
              (reference / 'a.star').read_text().rstrip(), 'explicit receipts changed existing saved-model blocks')
    # Power the full-header comparison on nonvolatile labels and extended bytes.
    raw = bytearray((reference / 'a.mrc').read_bytes()); mutant = work / 'header-mutant.mrc'
    raw[304] ^= 1; mutant.write_bytes(raw)
    t.require(image_fingerprint(mutant) != image_fingerprint(reference / 'a.mrc'), 'nonvolatile label mutant escaped comparison')
    raw = bytearray((reference / 'a.mrc').read_bytes()); struct.pack_into('<i', raw, 92, 4)
    raw[1024:1024] = b'ABCD'; mutant.write_bytes(raw); first = image_fingerprint(mutant)
    raw[1024] ^= 1; mutant.write_bytes(raw)
    t.require(image_fingerprint(mutant) != first, 'extended header mutant escaped comparison')
    t.healthy(binary, work, replacement, normal)
    t.require('data_motioncorr_processing' not in (replacement / 'a.star').read_text(), 'ordinary rerun retained old receipt')
    before = t.snapshot(replacement)
    failed = t.invoke(binary, work, replacement, {**normal, '--only_do_unfinished': True})
    t.require(failed.returncode > 0 and 'complete legacy output has no processing receipt' in failed.stderr and
              '--write_resume_receipts' in failed.stderr, 'strict resume silently accepted ordinary completed output')
    t.require(t.snapshot(replacement) == before, 'legacy refusal mutated outputs')
    # Gain alias prevention remains active without computing any digest, even
    # with supported Image format selectors (same physical source file).
    alias = work / 'alias'; alias.mkdir()
    write_mrc(alias / 'gain.mrc', [[1.0] * (96 * 96)], nx=96, ny=96)
    for suffix in ('', ':mrc'):
        before = t.snapshot(alias)
        failed = t.invoke(binary, work, alias, {**normal, '--gainref': str(alias / 'gain.mrc') + suffix, '--gain_rot': '1'})
        t.require(failed.returncode > 0 and 'aliases immutable gain source' in failed.stderr, 'ordinary gain alias escaped cheap protection')
        t.require(t.snapshot(alias) == before, 'ordinary gain alias mutated source')
    # An ordinary late-write failure must invalidate an old strict marker too.
    late = work / 'late'; options = {**t.PRODUCTS, '--gainref': str(gain)}
    t.healthy(binary, work, late, options)
    joint = (late / 'corrected_micrographs.star').read_bytes()
    (late / 'a_ODD.mrc').unlink(); (late / 'a_ODD.mrc').mkdir()
    failed = t.invoke(binary, work, late, {**options, '--write_resume_receipts': False})
    t.require(failed.returncode > 0 and 'a_ODD.mrc' in failed.stderr and not (late / 'a.star').exists(),
              'ordinary late failure retained old receipt/completion')
    t.require((late / 'corrected_micrographs.star').read_bytes() == joint, 'ordinary late failure published joint success')
    if mutation_shim:
        for kind in ('gain', 'executable'):
            for sync in (False, True):
                changed = work / ('changed-' + kind + '-' + str(sync)); changed.mkdir()
                t.fixture(changed)
                private_binary = changed / 'motioncorr-private'; shutil.copy2(binary, private_binary)
                private_gain = changed / 'gain.mrc'
                write_mrc(private_gain, [[1.0] * (96 * 96)], nx=96, ny=96)
                out = changed / 'out'; source = private_gain if kind == 'gain' else private_binary
                replacement = changed / 'replacement'; shutil.copy2(private_binary, replacement)
                before_inode = source.stat().st_ino; before = source.read_bytes()
                witness = changed / 'mutation.log'
                env = dict(os.environ)
                env['DYLD_INSERT_LIBRARIES' if sys.platform == 'darwin' else 'LD_PRELOAD'] = str(mutation_shim)
                env.update(MC_RECEIPT_MUTATE_AFTER_CLOSE=str(out / 'a.mrc'), MC_RECEIPT_MUTATE_INPUT=str(source),
                           MC_RECEIPT_MUTATION_WITNESS=str(witness), MC_RECEIPT_MUTATION_KIND=kind,
                           MC_RECEIPT_REPLACEMENT=str(replacement))
                result = subprocess.run(t.command(private_binary, out, {'--write_resume_receipts': False,
                                        '--gainref': str(private_gain), '--sync_output': sync}),
                                        cwd=changed, env=env, capture_output=True, text=True, timeout=60)
                t.require(witness.is_file() and witness.read_text() == 'ACTUAL_SOURCE_CHANGED_AFTER_IMAGE_CLOSE\n',
                          'ordinary mutation seam not actually reached')
                t.require(source.stat().st_ino != before_inode if kind == 'executable' else source.read_bytes() != before,
                          'ordinary mutation did not change source identity/content')
                t.require(result.returncode == 0 and (out / 'a.star').is_file() and (out / 'corrected_micrographs.star').is_file(),
                          'ordinary changed source entered receipt publication check: ' + result.stderr)
                t.require('data_motioncorr_processing' not in (out / 'a.star').read_text(), 'changed-source ordinary run certified a receipt')
    count = t.CHECKS - checks_before
    print('PASS actual ordinary no-digest/no-receipt, explicit/implied faults, legacy refusal, alias and late-write controls: ' + str(count) + ' checks')
    return count


def main():
    p = argparse.ArgumentParser(); p.add_argument('--binary', type=Path, required=True); p.add_argument('--shim', type=Path, required=True)
    p.add_argument('--mutation-shim', type=Path); p.add_argument('--work', type=Path); p.add_argument('--predecessor', action='store_true'); a = p.parse_args()
    if a.work: run(a.binary.resolve(), a.shim.resolve(), a.work.resolve(), a.predecessor, a.mutation_shim.resolve() if a.mutation_shim else None)
    else:
        with tempfile.TemporaryDirectory(prefix='receipt-default-') as directory:
            run(a.binary.resolve(), a.shim.resolve(), Path(directory).resolve(), a.predecessor, a.mutation_shim.resolve() if a.mutation_shim else None)
    print('PASS default mode ' + str(t.CHECKS) + ' explicit checks')


if __name__ == '__main__': main()
