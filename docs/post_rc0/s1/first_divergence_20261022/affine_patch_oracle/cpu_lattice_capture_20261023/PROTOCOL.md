# W4 affine lattice: CPU-only capture, iteration 1

Parent-frozen before writing the driver or launching any new native process.
Base: `22675db7e645d745203f8e5fe3507c4999448473`. This is the CPU half of the
retained 16-process proposal, under the user's instruction to continue CPU work
and reviews while GPU work is paused. The original proposal and evidence stay
unchanged. Its eight CUDA captures remain HELD/UNRUN.

## Question and predictions

Capture the other eight patches of the affine 3x3 lattice, to enable a later
observation/fit diagnosis. The retained CPU patch (2,1) is not repeated. Capture
acceptance requires exit 0, exactly the requested local patch metadata, and
unchanged products, global state and model versus the retained #275 affine CPU
capture. The selector does not enter numerical computation, so every comparison
is expected to pass. A successful capture is not motion-truth acceptance.

No oracle, fit, field metric or new accuracy claim is computed in this stage.
Those require a separate prospective analysis using the original controls and
truth gates. Historical **2 PASS / 10 FAIL / 4 UNIDENTIFIABLE** stays unchanged.

## Immutable inputs and execution

`protocol.json` pins the retained source archive, overlay archive and patch,
patched source files, CPU binary, fixture manifest and affine input files, and
six baseline state/product files. They are read in place under
`/mnt/clathrin/alex-motioncorr-residual-ccf-20261022-805d9de2`; the old scratch
is never written. Check every binding before and after the campaign. A missing
input or mismatch stops without rebuilding, regenerating or reselecting.

Exactly eight serial MotionCorr invocations, in this order, with 1-based (y,x)
selectors: (1,1), (1,2), (1,3), (2,2), (2,3), (3,1), (3,2), (3,3).
Use the retained CPU binary (sha256 `778ca7d5...dfb5df1`), working directory
`OLD/fixtures`, and the unchanged #275 argv:

```text
OLD/build-cpu/motioncorr --i affine.star --o NEW/PATCH/out --use_own --j 1
  --patch_x 3 --patch_y 3 --bin_factor 1 --seed 1 --skip_defect --save_noDW
  --first_frame_sum 1 --last_frame_sum 5 --skip_logfile
```

Clear inherited `MC_DIAG_*`, `MC_CCF_*` and `CUDA_*`; set
`MC_CCF_CAPTURE=NEW/PATCH/capture`, `MC_CCF_STATE=NEW/PATCH/state`, and
`MC_CCF_PATCH=y,x`. Set `CUDA_VISIBLE_DEVICES` empty; numeric thread variables
to 1; `LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64`, matching the retained run.
No `--gpu`, GPU query, build, package install, science job or timing claim.

On 4-gpu-vm, UID1004, CPU13 only, numeric/runtime threads1, within the existing
8-CPU allocation (C1 8-9, DC 10-12, M4 formerly14-15). Parent reserves CPU13
against guard regrading until this campaign releases it. Refresh occupancy and
free space immediately before launch. Acquire `/tmp/motioncorr-w4-cpu13.lock`
nonblocking and hold through final identity check and reap. Refuse another
same-user MotionCorr process whose affinity includes CPU13. Fresh scratch must
not exist, must be outside OLD on `/mnt/clathrin`, cap64MiB, at least1GiB free.
No lock wait, retry or change to a foreign process.

## Frozen checks and stop rule

Each process has a 120-second bound. Record argv, cwd, selected environment,
source/binary/input hashes, PID/birth, affinity, timestamps and exit status.
On timeout, stop only the unreaped direct CPU child, retain failure, and launch
no further patch. No retry is allowed. Record the original failed invocation.

Require `c1.json` global and `c2.json` local captures with frames5; the local
selector must equal the requested patch and tag `cpu`. Require nonempty capture
arrays and no additional local-call metadata. Capture inventory/hashes and all
logs/state/products are retained.

For neutrality, compare the entire STAR and MRC/MRCS relative inventories with
the retained `runs/cpu-affine-on/out`. STAR bytes must be exact after replacing
only the old/new output prefix. `state/global.txt` and `state/model.txt` must be
byte-identical. MRC/MRCS bytes `[0:224]+[1024:]` must be exact; label bytes
`[224:1024]` must be exact after only the existing #275 Relion timestamp regex
substitution. There is no numerical tolerance or other normalization. Require
the input/source/binary/baseline identities unchanged after each process and at
the end. Stop on any mismatch, nonzero exit, malformed/missing capture,
occupancy/space conflict or unexpected output change; retain it as FAIL and
leave remaining patches UNRUN. No acceptance criterion is weakened.

## Retention and next step

Commit the driver separately after this protocol freeze, then hash it and copy
the committed inputs into a new scratch namespace before the one campaign.
Retain raw data remotely and a hash-bound capture/evidence packet locally.
Publish only after independent review. A later all-patch oracle may use the
#276 fit path only with enough accepted observations and lattice coverage;
until then the fit remains UNRUN. This branch changes no production code,
metadata contract, policy, defaults or gates.
