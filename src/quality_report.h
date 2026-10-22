/***************************************************************************
 * Experimental per-movie alignment quality report (issue #268 prototype).
 *
 * Compiled only with -DMOTIONCORR_EXPERIMENTAL_QUALITY_REPORT=ON and active
 * only with --experimental_quality_report. It observes; it never changes a
 * product, trajectory, exit status or publication decision. The schema is an
 * unapproved prototype. See
 * docs/post_rc0/issue268_quality_prototype_20261023/DESIGN.md.
 *
 * This file is part of MotionCorr, distributed under the GNU General Public
 * License version 2 or later. See LICENSE.
 ***************************************************************************/
#ifndef MC_QUALITY_REPORT_H_
#define MC_QUALITY_REPORT_H_

#ifdef MC_EXPERIMENTAL_QUALITY_REPORT

#include <cmath>
#include <limits>
#include <string>
#include <vector>

namespace mcquality {

// What one solver call actually did. Filled only by the solver itself.
struct SolveRecord
{
	bool ran = false;          // false: the solver returned without iterating
	int iterations = 0;
	int max_iter = 0;
	double tolerance_px = 0;
	double final_rmsd_px = std::numeric_limits<double>::quiet_NaN();
	bool converged = false;
};

// The capture installed by the runner around a solver call. Thread-local
// because every alignment solver runs its convergence loop on the caller's
// thread; a null pointer (the default) makes recording a no-op.
extern thread_local SolveRecord *active_solve;

struct SolveCapture
{
	SolveRecord record;
	SolveRecord *previous;
	explicit SolveCapture(bool enabled) : previous(active_solve)
	{
		active_solve = enabled ? &record : nullptr;
	}
	~SolveCapture() { active_solve = previous; }
	SolveCapture(const SolveCapture &) = delete;
	SolveCapture &operator=(const SolveCapture &) = delete;
};

// Called by a solver after its iteration loop. iterations == 0 is not a run.
inline void noteSolve(int iterations, double final_rmsd_px, bool converged,
                      int max_iter, double tolerance_px)
{
	if (!active_solve) return;
	active_solve->ran = iterations > 0;
	active_solve->iterations = iterations;
	active_solve->final_rmsd_px = final_rmsd_px;
	active_solve->converged = converged;
	active_solve->max_iter = max_iter;
	active_solve->tolerance_px = tolerance_px;
}

struct Attempt
{
	std::string route;   // cpu, cuda_resident_patch, cuda_batched, cuda_host_staged
	std::string kind;    // first, same_input_retry
	SolveRecord solve;
	bool solver_returned = false;
};

struct PatchRecord
{
	int index = 0, iy = 0, ix = 0;
	bool device_preparation_declined = false;
	bool converged = false;
	std::vector<Attempt> attempts;
};

struct MovieQuality
{
	bool processed = false;  // this run computed (or tried to compute) the movie

	// Global alignment.
	bool global_started = false, global_finished = false;
	std::string global_route = "none";
	SolveRecord global_solve;
	bool global_returned = false;

	// Local alignment and model.
	std::string local_state = "not_assessed";  // attempted, not_requested
	int patches_planned = 0;
	std::vector<PatchRecord> patches;
	std::string model_state = "not_assessed";  // retained, global_only, not_requested
	std::string model_reason;
	int observations = -1;
	double largest_delta_px = std::numeric_limits<double>::quiet_NaN();
	double fit_rmsd_x_px = std::numeric_limits<double>::quiet_NaN();
	double fit_rmsd_y_px = std::numeric_limits<double>::quiet_NaN();

	// Publication, decided after the writer has drained.
	bool computation_ok = false;
	bool write_failed = false;
};

struct RunIdentity
{
	std::string run_id;
	std::string source_revision, source_dirty;
	std::string binary_sha256;
	std::string backend;
	int gpu_id = -1;
	std::vector<std::pair<std::string, std::string> > options;  // name, value text
	std::vector<std::string> argv;
};

// One entry per joint-membership movie, for the aggregate.
struct SummaryEntry
{
	std::string movie;
	std::string source;          // this_run, resumed_sidecar, unknown_legacy
	std::string reason;          // unknown_legacy reason
	std::string sidecar_path, sidecar_sha256;
	bool sidecar_write_failed = false;
	std::string sidecar_write_error;
	std::string global_state, local_model_state, publication_state;
};

std::string makeRunId();
std::string sha256File(const std::string &path);   // "" if unreadable
std::string selfBinarySha256();

std::string globalState(const MovieQuality &q);
std::string publicationState(const MovieQuality &q);

// Rename a regular file at path to <stem>.superseded-<run_id><ext>; leave
// anything else alone. Returns false (with message) if a rename failed.
bool supersede(const std::string &path, const std::string &run_id, std::string &error);

// Write the sidecar atomically. Returns false with an error message on failure.
bool writeSidecar(const std::string &path, const RunIdentity &id, const std::string &movie,
                  const MovieQuality &q, const std::string &star_path,
                  const std::string &micrograph_path, std::string &error);

// Validate a prior sidecar for a resumed (skipped, complete) movie and fill the
// entry's states, or set source=unknown_legacy with the reason.
void readResumedSidecar(const std::string &path, const std::string &movie,
                        const std::string &star_path, const std::string &micrograph_path,
                        SummaryEntry &entry);

bool writeSummary(const std::string &path, const RunIdentity &id,
                  const std::vector<SummaryEntry> &entries,
                  const std::string &joint_state, const std::string &joint_path,
                  std::string &error);

}  // namespace mcquality

#endif  // MC_EXPERIMENTAL_QUALITY_REPORT
#endif  // MC_QUALITY_REPORT_H_
