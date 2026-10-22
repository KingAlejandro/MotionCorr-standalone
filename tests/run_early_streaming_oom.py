#!/usr/bin/env python3
"""#226 D3: refuse below the Fourier-stack lower bound, then process movie b."""
import argparse
import re
from pathlib import Path
import tempfile

from test_gain_cache import NX, NY
from streaming_oom_test_support import prepare, reference, run, failed_products


def controls(binary, root):
    frames = prepare(root)
    expected = reference(binary, root)
    code, text, output = run(binary, root, 'early-refusal',
                            dict(MC_FAULT_ORDINAL='1', MC_AVAILABLE_BYTES='1'))
    required = len(frames) * NY * (NX // 2 + 1) * 8
    message = re.search(r'streaming global alignment requires at least (\d+) bytes; available 1 bytes', text)
    problems = failed_products(output, expected)
    if code != 1 or not message or int(message[1]) < required:
        problems.append('missing ordinary early named OOM failure with required lower bound')
    if 'incompatible' in text.lower():
        problems.append('misleading incompatible-GPU diagnostic')
    if problems:
        raise AssertionError(f'{problems}\n{text}')
    print('PASS: early named OOM, no failed/joint products, next movie identical')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--root', type=Path, help='new retained evidence directory')
    args = parser.parse_args()
    if args.root:
        controls(args.binary.resolve(), args.root.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='mc-early-oom-') as temp:
            controls(args.binary.resolve(), Path(temp) / 'controls')


if __name__ == '__main__':
    main()
