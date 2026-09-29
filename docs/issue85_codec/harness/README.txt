Scripts exactly as they ran on cpu64, from /home/ubuntu/mc-i85-codec-20260929.
They carry that absolute path and a hardcoded expected binary hash; they are a
record of what executed, not a portable tool. See ../validation.txt for the
revisions, hashes and resources they ran against.

  codec_witness.c    LD_PRELOAD interposer counting zlib vs libdeflate calls
  probe_subcodec.c   standalone form of the configure-time capability check
  bench.sh           the 10 matched full-application runs
  aggregate.py       bench output -> ../results.json
  parity.py          cross-arm product identity plus its negative controls
  validate.sh        rebuild, probe controls, witness, suites, parity
