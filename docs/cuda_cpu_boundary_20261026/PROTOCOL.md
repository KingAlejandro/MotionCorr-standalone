# Native capture/replay contract

Reviewed hook: `7a1bde5db99c94bc4332bae3f3aff6e0bfccaabd`. Normal
build: RFLOAT double, fComplex two adjacent float32 (real, imaginary),
little-endian host. GPU2 A10080GB PCIe, CUDA12.8, CPU80-87, --j8.
Only two complete movies, same gain/input hashes and one-movie STAR per case.
No interpolation-origin option, no DC or coupled-peak hook enabled.

Backend selectors: CPU = same CUDA-enabled binary without --gpu, with
CUDA_VISIBLE_DEVICES empty; native CUDA = --gpu0 with CUDA_VISIBLE_DEVICES
bound to GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598. Plain CUDA, --ingest float
(no nvCOMP). Record actual ingest witness, resident forward/global/local log
markers, and nvidia-smi process/UUID samples. No FFTW hybrid or output copying.

Layout: real arrays unshifted row-major [ny,nx], floats; half-spectra
[ny,nx/2+1], complex64. CCF windows [ccf_ny,ccf_nx/2+1]; window row y maps
to original y for y<=ccf_ny/2, otherwise y-ccf_ny+ny. The array shapes and
B/search range are in geometry.txt. input-F files cover all24 original frame
windows; full forward FFT and preprocessing cover frames0/4. CCF maps and
spectra cover iteration1 frames0/4. Raw peak shifts are before frame0 anchor
subtraction, float64 CPU / float32 CUDA. Preserve both numerical and bit equality.

Normalization: CPU NewFFT float32 FwdOnly forward divides each complex value
by float32(nx*ny); inverse is unscaled. No FFTW threads library is linked or
fftwf_init_threads/plan_with_nthreads called: each plan is single-threaded,
--j8 provides outer OpenMP frame parallelism. NewFFT uses alignment-specific
cached FFTW_ESTIMATE plans, rank2 [ny,nx], out-of-place. Replay prints a separately constructed FFTW_ESTIMATE forward plan with the
same dimensions/alignment; that print is not an executed-plan-instance witness.
Actual NewFFT execution uses its cached dispatch; exact same-backend array
reproduction is checked separately. Native resident forward = CudaMovieSession,
rank2 cuFFT R2C batch1 per frame, shared manually allocated workspace;
float32 reciprocal scale kernel after all frames. Native CCF inverse =
rank2 cuFFT C2R batch24 with packed distances, unscaled; the native global
workspace may borrow dead real-frame storage. Versions/linkage retained.

`spectrum-F.c64` = raw weighted CCF spectrum. `ifft-input-F.c64` = actual
consumer input: raw preserving NewFFT wrapper input on CPU; after actual
mc_cuda::projectHermitianColumns on CUDA. Raw half-spectra are NOT assumed
Hermitian valid. Quantify x=0/Nyquist conjugacy errors and projection changes.
Crossed inverse replay starts each backend with the SAME hashed saved raw
spectrum; CUDA applies its native consumption projection and records its output.
A second CPU inverse of those projected bytes separates projection from FFT.
No spectrum is borrowed from an already-diverged later trajectory.

Window replay reads all24 saved CCF-window inputs. CPU replay duplicates only
first reference/weight/CCF construction with fComplex and calls actual NewFFT;
its same-backend captured ref/weights/spectra/maps must reproduce exactly before
cross-backend interpretation. CUDA replay invokes actual
cudaAlignPatchDeviceWithWorkspace(windowed=true,max_iter1,is_global=true),
original pnx/pny/B and automatic CCF scale; original dimensions/geometry must
match. CCF batch/plan/packed layout retained. Window mode exactness is checked
against the native capture, not assumed. The default unique/tied peak hypotheses
remain separate, as does optional interpolation-origin semantics (UNRUN).

Forward replay reads identical saved preprocessed frames0/4, runs actual NewFFT
or a native CudaMovieSession with original24-frame allocation (other frames
zero; transforms are independent), no gain/statistics/estimation rerun. Native
same-backend equality must hold before this supports first-FFT attribution.
Replay output is never a MotionCorr product or an acceptance result.
