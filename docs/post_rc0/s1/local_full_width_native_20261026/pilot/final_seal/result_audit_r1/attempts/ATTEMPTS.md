attempt 1 (02_independent_metrics.py): system python3 -I has no numpy -> ModuleNotFoundError, no output. Rerun with a numpy-bearing interpreter.
attempt 2: interpreter /Users/alex.konstantinov/.local/share/uv/python/cpython-3.13.7-macos-aarch64-none/bin/python3 numpy 2.4.2
attempt 3 (03_mechanical.py v1): rc 0, but two auditor-script defects, outputs kept in attempts/03_mechanical_v1.*:
  (a) problem filter flagged every boolean field equal to False (timed_out=false, local_enabled=false on 1x1) as a failure;
  (b) DECISION.pair_record_sha256 compared with raw pair.json bytes; the producer hashes canonical JSON (sort_keys, compact separators) -
      verified in an ad-hoc check: canonical matches, raw/indent variants do not. Fixed in 03_mechanical_v2.py.
