/***************************************************************************
 *
 * Author: "Sjors H.W. Scheres"
 * MRC Laboratory of Molecular Biology
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * This complete copyright notice must be included in any revised version of the
 * source code. Additional authorship citations may be added, but existing
 * author citations must be preserved.
 ***************************************************************************/

#ifndef MOTIONCORR_RUNNER_H_
#define MOTIONCORR_RUNNER_H_

#include <glob.h>
#include <vector>
#include <string>
#include <stdlib.h>
#include <stdio.h>
#include <algorithm>
#include <functional>
#include <memory>
#include <thread>
#include <src/time.h>
#include "src/output_writer.h"
#include "src/metadata_table.h"
#include "src/image.h"
#include "src/micrograph_model.h"
#include <src/jaz/single_particle/obs_model.h>
#include "src/jaz/tomography/tomogram_set.h"

class EERRenderer;

#ifdef _CUDA_ENABLED
#include <cufft.h>
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/acc/cuda/cuda_realspace_dw.h"
#endif

// Which movie ingest path executeOwnMotionCorrection() may use.
//
// INGEST_AUTO is production: the fastest applicable path is chosen per movie.
// The other three exist so an ablation arm, or a support-matrix row, can pin
// the path and FAIL when it is unavailable rather than quietly running on a
// different one. IOParser treats an unrecognised flag as a warning, so an arm
// that merely passes a flag proves nothing; an arm that errors when its path
// did not run proves the path ran.
enum MovieIngestMode
{
	INGEST_AUTO = 0,
	INGEST_NVCOMP,   // require the nvCOMP device ingest
	INGEST_COMPACT,  // require the compact host uint16 staging
	INGEST_FLOAT     // require main's float host reader
};

class MotioncorrRunner
{
public:

	// I/O Parser
	IOParser parser;

	// Verbosity
	int verb;

	// Number of threads per process
	int n_threads;
	int max_io_threads;

	// Write each movie's products on the calling thread instead of handing them
	// to the background OutputWriter. The two paths produce the same products in
	// the same order; this exists so the writer can be ablated against an
	// otherwise identical binary, and as an escape hatch on a host where the
	// extra thread costs more CPU than the overlap buys.
	bool sync_output = false;
	// --profile: JSON-lines stage profile path; empty disables it.
	FileName fn_profile;
	// How main() configured the host allocator; printed once and in --profile.
	std::string host_allocator_mode;

	// Pinned ingest path; see MovieIngestMode. Default INGEST_AUTO is production.
	MovieIngestMode ingest_mode = INGEST_AUTO;

	// Opt-in diagnostic: append "<movie> <path>" per movie. Empty by default, so
	// a normal run writes nothing extra and no product changes. This is how an
	// --ingest auto run over a mixed-format set is checked to have routed each
	// movie to the path it should have.
	FileName fn_ingest_witness;

	// Output rootname
	FileName fn_in, fn_out, fn_movie;

	// Filenames of all the micrographs to run Motioncorr on
	std::vector<FileName> fn_micrographs, fn_ori_micrographs;

	// Optics group number for all original micrographs
	std::vector<int> optics_group_micrographs, optics_group_ori_micrographs;

    // Pre-exposure for each micrograph (mainly used for tomography)
    std::vector<RFLOAT> pre_exposure_micrographs, pre_exposure_ori_micrographs;

    // Expected frame count per micrograph (from STAR metadata or --expected_frames)
    std::vector<int> expected_frames_micrographs;

	// Information about the optics groups
	ObservationModel obsModel;

    // Is this a tomography experiment?
    bool is_tomo;

    // Information about tomography experiment
    TomogramSet tomogramSet;

    // Skip generation of logfile
	bool do_skip_logfile;

	// Use our own implementation
	bool do_own;
	bool interpolate_shifts;

	// Write in float16 (MRC mode 12)?
	bool write_float16;

	// Maximum number of iterations
	int max_iter;

	// Save aligned but non-dose weighted micrograph.
	// With MOTIONCOR2, this flag is always assumed to be true
	bool save_noDW;

	// Use MOTIONCOR2 instead of UNBLUR?
	bool do_motioncor2;

	// First and last movie frames to use in alignment and written-out corrected average and movie (default: do all)
	int first_frame_ali, last_frame_ali, first_frame_sum, last_frame_sum;

	// Expected number of frames per movie (from --expected_frames, default: -1)
	int expected_frames = -1;

	// Group this number of frames and write summed power spectrum. -1 == do not write
	int grouping_for_ps;
	int ps_size;

	// Binning factor for binning inside MOTIONCORR/MOTIONCOR2
	double bin_factor;

	// Do binning before processing
	bool early_binning;

	// B-factor for MOTIONCOR2
	double bfactor;

	// Downsampling rate of CCF
	double ccf_downsample;

	// Dose at which to distinguish between early/late global motion in output statistics
	double dose_motionstats_cutoff;

	// Additional arguments that need to be passed to MOTIONCORR
	FileName fn_other_motioncor2_args;

	// MOTIONCOR2 executable
	FileName fn_motioncor2_exe;

	// Voltage and dose per frame for MOTIONCOR2/UNBLUR dose-weighting
	bool do_dose_weighting;
	double voltage;
	double dose_per_frame;
	double pre_exposure;

	// Gain reference file
	FileName fn_gain_reference;

	// The gain reference is fixed for a whole run (prepareGainReference resolves
	// fn_gain_reference once, before the movie loop), so it is read from disk on
	// the first movie and reused afterwards. Keyed on the geometry as well as the
	// path: a movie of different dimensions, or a different EER upsampling, must
	// miss and reload rather than silently reuse a wrongly sized array.
	// A member rather than a file-static: the movie loop is serial, so this needs
	// no synchronisation, and that reasoning stays checkable.
	Image<float> gain_cache;
	FileName gain_cache_name;
	int gain_cache_nx = 0, gain_cache_ny = 0;
	bool gain_cache_is_eer = false;
	int gain_cache_eer_upsampling = 0;
	bool gain_cache_filled = false;
	// Bumped on every refill of gain_cache, from a process-wide counter. Lets the
	// CUDA session tell "same gain array as last movie" from "refilled, possibly
	// different contents" without hashing 54 MiB per movie. 0 means "no identity
	// resolved yet", which disables device-side retention. The counter is global
	// rather than per-runner so that two runners on one worker thread cannot mint
	// the same generation for different gain contents.
	unsigned long long gain_cache_generation = 0;

	// True when gain_cache_generation is a valid identity for a movie of this
	// geometry, i.e. gainReferenceFor() has already resolved the gain for this
	// movie. The device retention key is only sound under that ordering, so the
	// caller asserts this instead of leaving the ordering implicit.
	bool gainIdentityResolvedFor(int nx, int ny) const;

	// Static defect pre-mask cache: exact TXT bytes, path, gain generation and
	// geometry. TXT parsing consumes the keyed snapshot. Image defect maps use
	// the original per-movie reader and are not cached. Detected hot pixels are
	// never cached here.
	MultidimArray<bool> defect_premask;
	FileName defect_premask_fn;
	std::string defect_premask_defect_bytes;
	FileName defect_premask_gain_fn;
	unsigned long long defect_premask_gain_gen = 0;
	int defect_premask_nx = 0, defect_premask_ny = 0;
	bool defect_premask_valid = false;

	// Returns the static pre-mask, rebuilding it on a key miss. The returned
	// reference is owned by this runner; callers that add detected hot pixels
	// must copy it first.
	const MultidimArray<bool>& getDefectPremask(int nx, int ny, const FileName &fn_defect,
	                                            const FileName &fn_gain_reference,
	                                            const MultidimArray<float> &Igain,
	                                            int n_threads);
	bool isDefectPremaskValid() const { return defect_premask_valid; }

	// Returns the gain for this movie, reading it only on a cache miss.
	// Const so the read-only invariant is enforced by the compiler: callers must
	// not mutate shared state that every later movie will reuse.
	const MultidimArray<float>& gainReferenceFor(bool is_eer, EERRenderer &renderer,
	                                             int nx, int ny);
	int gain_rotation, gain_flip;

	// Defect file
	FileName fn_defect;

	// Skip hot pixel detection in own motioncorr
	bool skip_defect;

	// Random seed for hot pixel replacement (deterministic across threads)
	int random_seed = 1;

	// Archive directory
	FileName fn_archive;

	// Number of patches in X, Y direction for MOTIONCOR2
	int patch_x, patch_y;

	// How many frames to group in MOTIONCOR2
	int group;

	// Pixel size for UNBLUR
	double angpix;

	// Continue an old run: only estimate CTF if logfile WITH Final Values line does not yet exist, otherwise skip the micrograph
	bool continue_old;

	// Process at most this number of (unprocessed) micrographs
	long do_at_most;
	
	// Save sums of movies from even and odd frames for denoising
	bool even_odd_split;
	
	// EER parameters
	int eer_upsampling, eer_grouping;

	// Output STAR file
	MetaDataTable MDavg, MDmov;

	// Which GPU devices to use?
	int devCount;
	std::string gpu_ids;
	std::vector < std::vector < std::string > > allThreadIDs;
	bool use_gpu;
	int gpu_id;

	// Read command line arguments
	void read(int argc, char **argv, int rank = 0);

	// Print usage instructions
	void usage();

	// Initialise some stuff after reading
	void initialise();

	void prepareGainReference(bool write_gain);

	// Execute all MOTIONCORR jobs
	void run();

	// Given an input fn_mic filename, this function will determine the names of the output corrected image (fn_avg) and the corrected movie (fn_mov).
	FileName getOutputFileNames(FileName fn_mic, bool continue_even_odd = false);
	bool isMovieComplete(const FileName &movie, int effective_expected_frames = -1);

	// Execute MOTIONCOR2 for a single micrograph
	bool executeMotioncor2(Micrograph &mic, int rank = 0);

	// Get the shifts from MOTIONCOR2
	void getShiftsMotioncor2(FileName fn_log, Micrograph &mic);

	// Execute our own implementation for a single micrograph
	bool executeOwnMotionCorrection(Micrograph &mic, int effective_expected_frames = -1);

	// Plot the shifts
	void plotShifts(FileName fn_mic, Micrograph &mic);

	// Save micrograph model. Equivalent to stampModel() then writeModel().
	void saveModel(Micrograph &mic);

	// Copy the runner's current per-movie metadata onto the model. run()
	// re-reads angpix and voltage from the optics table for every movie, so
	// this has to happen on the thread that owns that state.
	void stampModel(Micrograph &mic);

	// Serialise an already-stamped model. Reads only setup-time state, so it
	// is safe to run on the output writer thread.
	void writeModel(Micrograph &mic);

	// Make a PDF file with all the shifts and write output STAR files
	void generateLogFilePDFAndWriteStarFiles();

	// Write out final STAR file
	void writeSTAR();

	// Read fn_defect (defect map, where 1 is bad, or defect text in the UCSF MotionCor2 format, x y w h) and fill bBad.
	static void fillDefectMask(MultidimArray<bool> &bBad, FileName fn_defect, int n_threads=1);

	// Check if fn_defect is Serial EM's defect file
	static bool detectSerialEMDefectText(FileName fn_defect);

	// Test-only access to the private alignment entry point. Used by
	// tests/test_patch_retry_state.cpp to characterise the shift-accumulation
	// contract behind issue #69 against the production function rather than a copy
	// of it. A friend declaration emits no code and changes no behaviour.
	friend struct MotioncorrRunnerTestAccess;
	// Inter-/extrapolate per-group local shifts onto every frame.
	// Pure function of its arguments (reads no member state), hence static; public
	// so the motion-model arithmetic can be unit tested directly.
	static void interpolateShifts(std::vector<int> &group_start, std::vector<int> &group_size,
	                       std::vector<RFLOAT> &xshifts, std::vector<RFLOAT> &yshifts,
	                       int n_frames,
	                       std::vector<RFLOAT> &interpolated_xshifts, std::vector<RFLOAT> &interpolated_yshifts);

	// Recenter per-frame shifts so that frame 0 becomes the origin.
	// The first-frame offset MUST be saved before the in-place subtraction begins,
	// otherwise iteration zero zeroes the origin that later iterations still need.
	static void recenterShiftsToFirstFrame(std::vector<RFLOAT> &xshifts, std::vector<RFLOAT> &yshifts);

private:
	// Background output writer, created by run() for the duration of the movie
	// loop. Null elsewhere -- including in a default-constructed runner -- and
	// submitOutput() then runs the task inline, so every entry point that is
	// not run() keeps the plain serial behaviour.
	std::unique_ptr<OutputWriter> output_writer;
	long int output_movie_index = -1;

#ifdef _CUDA_ENABLED
	// The previous movie's CUDA session, parked for the next movie of the same
	// geometry (docs/cuda_session_reuse.md). Non-null only between movies; the
	// next movie takes or releases it before allocating anything on the device.
	std::unique_ptr<CudaMovieSession> parked_cuda_session;
	// Checked release of the parked session. Returns false, after writing the
	// failure to std::cerr, when the release recorded a CUDA failure.
	bool releaseParkedCudaSession(const char *boundary);
	// First-movie warm-up: creates the primary context on gpu_id while the main
	// thread parses movie 0 and reads the gain. It calls only cudaSetDevice and
	// discards the result; the main thread repeats every call it depends on, so
	// any failure is still reported there with the same message. Joined before
	// the first session setup and on every exit from run().
	struct JoinOnDestroy {
		std::thread t;
		~JoinOnDestroy() { if (t.joinable()) t.join(); }
	} cuda_context_warmup;
	void joinCudaContextWarmup();
#endif

	// Hand one output product to the writer, or write it here when there is
	// none. Products of one movie are written in submission order.
	void submitOutput(std::function<void()> task);

	// Drain the writer's deferred failures: report each one, mark its movie
	// failed, and append the truth to that movie's log.
	void collectWriteFailures(std::vector<char> &movie_failed);

	// Take over @p image's pixels and write them to @p path. The caller's
	// image is left empty: a micrograph is ~57 MB and copying one per output
	// would cost more than the write it is trying to hide.
	void submitImageWrite(Image<float> &image, const FileName &path, DataType datatype);

	// shiftx, shifty is relative to the (real space) image size
	void shiftNonSquareImageInFourierTransform(MultidimArray<fComplex> &frame, RFLOAT shiftx, RFLOAT shifty);

	bool alignPatch(std::vector<MultidimArray<fComplex> > &Fframes, const int pnx, const int pny, const RFLOAT scaled_B, std::vector<RFLOAT> &xshifts, std::vector<RFLOAT> &yshifts, std::ostream &logfile, bool is_global = false);
#ifdef _CUDA_ENABLED
	bool alignPatchDevice(cufftComplex *d_Fframes, int n_frames, const int pnx, const int pny, const RFLOAT scaled_B, std::vector<RFLOAT> &xshifts, std::vector<RFLOAT> &yshifts, std::ostream &logfile, bool is_global = false);
#endif

	void binNonSquareImage(Image<float> &Iwork, RFLOAT bin_factor);

	int findGoodSize(int request);

	void doseWeighting(std::vector<MultidimArray<fComplex> > &Fframes, std::vector<RFLOAT> doses, RFLOAT apix);

	void realSpaceInterpolation(Image <float> &Isum, std::vector<Image<float> > &Iframes, MotionModel *model, std::ostream &logfile);

	void realSpaceInterpolation_ThirdOrderPolynomial(Image <float> &Isum, std::vector<Image<float> > &Iframes, ThirdOrderPolynomialModel &model, std::ostream &logfile);
	
	void realSpaceInterpolation_withoutsum(std::vector<Image<float> > &Ialignedframes, std::vector<Image<float> > &Iframes, MotionModel *model, std::ostream &logfile);

	void realSpaceInterpolation_ThirdOrderPolynomial_withoutsum(std::vector<Image<float> > &Ialignedframes, std::vector<Image<float> > &Iframes, ThirdOrderPolynomialModel &model, std::ostream &logfile);

};


#endif /* MOTIONCORR_RUNNER_H_ */
