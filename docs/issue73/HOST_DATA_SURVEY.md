# Host data survey — is an independent collection already staged? (#73)

Date: 2026-09-27. Read-only. No data copied, no other user's files or processes altered.

**Answer: no.** Every raw movie set reachable on Alex-owned storage is the same 24
beta-galactosidase RELION tutorial movies used by PR #65. An independent collection must be
acquired from a public archive.

This confirms, from the hosts themselves, PR #65's stated limitation that "no independent second
dataset exists on the project hosts".

## Hosts inspected

| Host | Role | State at survey |
| --- | --- | --- |
| `cpu64` (`small-refmac-machine`) | CPU builds / reference / validation | 64 cores, load 2.03, 216 GiB RAM free, **204 GiB disk free**. Two `ctffind` processes (another thread's work), unpinned but ~2 cores total. |
| `4GPUs` (`4-gpu-vm`) | shared GPU fallback | 4× A100 80 GB, all ~idle. 781 GiB free on `/`. |
| `scarf` | preferred GPU via Slurm | reachable; `/home/vol05` **2.4 TiB free**. Login connections reset intermittently — use one multiplexed connection. |

## Raw movie sets found

All raw movies on `4GPUs` are the same 24 tutorial movies, in four copies:

```
/home/alex/relion-container-tests/data/spa-relion30-tutorial/Movies      24 .tif + gain.mrc
/home/alex/relion-container-tests/projects/spa-onedep-dsp-20260612/Movies
/home/alex/relion-container-tests/projects/spa-onedep-dsp-20260612-fixed/Movies
/home/alex/relion-container-tests/projects/betagal-builder-repro-smoke-.../Movies
/home/alex/MotionCorr-standalone/relion30_tutorial/Movies
```

`cpu64` holds no raw movie collection beyond the same tutorial data and the #60 perturbation
outputs derived from it.

## Other collections present, and why each is unusable

### `/mnt/clathrin` (619 GiB, `4GPUs`) — clathrin-auxilin, K3 / 300 kV

Genuinely a different specimen and detector, so it was checked carefully. It contains **no raw
movies and no gain reference**:

- `2026-07-13-download/Katie_processing/` — Scipion/RELION job tree: `ProtRelionRefine3D`,
  `ProtRelionPostprocess`, `ProtRelionCreateMask3D`, `Particles_localrec/`, `Extract/`.
- Per the depositor's own `07-07-26_KWood_directorystructure` note, the inputs are "raw extracted
  particles from localised reconstruction" — `subparticle.mrcs` stacks, i.e. already extracted.
- `find` for `*.tif`, `*.tiff`, `*.eer`, `*movie*`, `*gain*` across the tree returned **nothing**
  except `hubs/MTF_curve_K3_300kv.star`.

Motion correction cannot be run on extracted particles. This collection **cannot** substitute for
a raw-movie comparison and is not used. It is also another user's unpublished data with no stated
licence.

### `/mnt/milan_xval/empiar_data/11233` (16.5 GiB, `4GPUs`) — TRPM8

Permission-restricted to another user (`dxp41838`). **Recorded as unavailable; no escalation
attempted and none appropriate.** Independently, the EMPIAR entry is a *final particle stack*
(`..._finalParticleStack_EMPIAR_stack.mrcs`) plus `emd_0639.mrc` — no raw movies — so it would not
have been usable regardless.

### `/home/alex/irrmc_download` (94 GiB, `4GPUs`)

IRRMC macromolecular **crystallography** diffraction data (`.h5`). Not cryo-EM movies.

### `/home/alex/relion-container-tests/sta-zenodo` (66 GiB, `4GPUs`)

RELION-5.0 **subtomogram averaging** tutorial results archive. Not SPA movies; out of scope for
this comparison.

## Consequence

The independent collection must come from a public archive. EMPIAR-12963 is selected; see
[`PROTOCOL.md`](PROTOCOL.md) §3 for the verification of its raw movies, gain, particle metadata,
licence and native-format support.
