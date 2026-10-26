// #268 quality-report prototype, unit controls U1-U4 (PROTOCOL_V2.md).
// Exercises src/quality_report.cpp directly; no MotionCorr process.
// Part of MotionCorr, distributed under the GNU General Public License version 2 or later.
#include "src/quality_report.h"

#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <unistd.h>

using namespace mcquality;

namespace {
int failures = 0;

void expect(bool ok, const std::string &what)
{
	std::cout << (ok ? "PASS " : "FAIL ") << what << std::endl;
	if (!ok) failures++;
}

std::string slurp(const std::string &path)
{
	std::ifstream in(path.c_str(), std::ios::binary);
	return std::string((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
}

void spit(const std::string &path, const std::string &text)
{
	std::ofstream(path.c_str(), std::ios::binary) << text;
}

bool contains(const std::string &text, const std::string &needle) { return text.find(needle) != std::string::npos; }

std::string replaced(std::string text, const std::string &from, const std::string &to)
{
	const size_t at = text.find(from);
	if (at == std::string::npos) { std::cout << "FAIL mutation anchor missing: " << from << std::endl; failures++; return text; }
	return text.replace(at, from.size(), to);
}

RunIdentity identity()
{
	RunIdentity id;
	id.run_id = "unit";
	id.source_revision = "unit";
	id.source_dirty = "false";
	id.binary_sha256 = "unavailable";
	id.backend = "cpu";
	id.argv = {"motioncorr", "--i", "in/batch.star"};
	return id;
}

// A completed, published movie: converged global, two completed patches, retained model.
MovieQuality healthy()
{
	MovieQuality q;
	q.processed = q.global_started = q.global_finished = q.global_returned = true;
	q.global_route = "cpu";
	q.global_solve.noted = q.global_solve.ran = q.global_solve.converged = true;
	q.global_solve.iterations = 2; q.global_solve.max_iter = 5; q.global_solve.tolerance_px = 0.5;
	q.global_solve.final_rmsd_px = 0.25;
	q.local_state = "attempted";
	q.patches_planned = 2;
	for (int i = 0; i < 2; i++) {
		PatchRecord p; p.index = i + 1; p.iy = 1; p.ix = i + 1; p.completed = true; p.converged = i == 0;
		Attempt a; a.route = "cpu"; a.kind = "first"; a.solve = q.global_solve; a.solve.converged = i == 0;
		p.attempts.push_back(a);
		q.patches.push_back(p);
	}
	q.model_state = "retained";
	q.observations = 25; q.min_observations_exclusive = 18;
	q.computation_ok = true;
	return q;
}
}  // namespace

int main()
{
	char dir_template[] = "/tmp/q268-unit-XXXXXX";
	const char *dir_created = mkdtemp(dir_template);
	if (!dir_created) { std::cerr << "mkdtemp failed" << std::endl; return 2; }
	const std::string dir = dir_created;
	const std::string movie = dir + "/movie.mrcs", star = dir + "/movie.star", mic = dir + "/movie.mrc";
	spit(movie, "movie-bytes"); spit(star, "star-bytes"); spit(mic, "mic-bytes");
	const RunIdentity id = identity();
	std::string error;

	// U1: an interrupted patch is neither converged nor dropped.
	{
		MovieQuality q = healthy();
		q.patches_planned = 3;
		PatchRecord p; p.index = 3; p.iy = 1; p.ix = 3;  // created, never completed
		q.patches.push_back(p);
		q.model_state = "not_assessed";
		q.computation_ok = false;
		const std::string path = dir + "/u1.json";
		expect(writeSidecar(path, id, movie, q, star, mic, error), "U1 sidecar written");
		const std::string text = slurp(path);
		expect(contains(text, "\"interrupted_patches\": 1") && contains(text, "\"dropped_patches\": 1") &&
		       contains(text, "\"converged_patches\": 1"), "U1 counts 1 converged / 1 dropped / 1 interrupted");
		expect(contains(text, "\"final\": \"interrupted\""), "U1 patch labelled interrupted");
		expect(contains(text, "\"local_alignment\": {\"state\": \"interrupted\""), "U1 local state interrupted");
		expect(contains(text, "\"reason\": \"movie_error\""), "U1 publication failed/movie_error");
		MovieQuality short_q = healthy();
		short_q.patches_planned = 9;  // fewer recorded than planned
		expect(writeSidecar(dir + "/u1b.json", id, movie, short_q, star, mic, error) &&
		       contains(slurp(dir + "/u1b.json"), "\"local_alignment\": {\"state\": \"interrupted\""),
		       "U1 fewer recorded than planned is interrupted");
	}

	// U2: ill-formed UTF-8 becomes the labelled hex object; well-formed text is unchanged.
	{
		expect(jsonText("in/z\xc3\xa9ro.mrcs") == "\"in/z\xc3\xa9ro.mrcs\"", "U2 well-formed UTF-8 preserved");
		expect(jsonText(std::string("in/zero\xe9.mrcs")) == "{\"non_utf8_bytes_hex\": \"696e2f7a65726fe92e6d726373\"}",
		       "U2 ill-formed byte encoded losslessly");
		expect(!wellFormedUtf8("\xc0\xaf") && !wellFormedUtf8("\xed\xa0\x80") && !wellFormedUtf8("\xf4\x90\x80\x80") &&
		       !wellFormedUtf8("\xe2\x82"), "U2 overlong, surrogate, >U+10FFFF and truncated rejected");
		expect(wellFormedUtf8("\xf0\x9f\x98\x80") && wellFormedUtf8("plain"), "U2 4-byte and ASCII accepted");
		expect(jsonText("a\"b\\c\n") == "\"a\\\"b\\\\c\\n\"", "U2 escapes kept");
		const std::string odd_movie = dir + "/zero\xe9.mrcs";
		spit(odd_movie, "odd");
		MovieQuality q = healthy();
		const std::string path = dir + "/u2.json";
		expect(writeSidecar(path, id, odd_movie, q, star, mic, error), "U2 sidecar written");
		const std::string text = slurp(path);
		expect(wellFormedUtf8(text) && contains(text, "\"non_utf8_bytes_hex\""), "U2 sidecar is well-formed UTF-8 with hex path");
		SummaryEntry entry;
		readResumedSidecar(path, odd_movie, star, mic, entry);
		if (std::ifstream(odd_movie.c_str()).good()) {
			expect(entry.source == "resumed_sidecar", "U2 hex-encoded path round-trips on resume");
		} else {
			// Some filesystems (APFS) refuse the name. The hex form must still parse
			// and validate; only the binding to the absent file can fail.
			std::cout << "NOTE U2 filesystem refused the ill-formed name; full round trip not exercised here" << std::endl;
			expect(entry.source == "unknown_legacy" && entry.reason == "sidecar_stale",
			       "U2 hex-encoded path validates (stale only because the file is absent)");
		}
	}

	// U3: resume accepts only a fully valid, bound v1 sidecar.
	{
		const std::string good = dir + "/movie.quality.json";
		expect(writeSidecar(good, id, movie, healthy(), star, mic, error), "U3 baseline written");
		const std::string base = slurp(good);
		SummaryEntry entry;
		readResumedSidecar(good, movie, star, mic, entry);
		expect(entry.source == "resumed_sidecar" && entry.global_state == "converged" &&
		       entry.local_model_state == "retained" && entry.publication_state == "published", "U3 untouched accepted");

		struct Case { const char *name, *from, *to, *reason; };
		const Case cases[] = {
			{"BOGUS global state", "\"state\": \"converged\"", "\"state\": \"BOGUS\"", "sidecar_invalid"},
			{"identifiable claim", "\"motion_identifiability\": \"not_assessed\"", "\"motion_identifiability\": \"identifiable\"", "sidecar_invalid"},
			{"peak validity claim", "\"peak_validity\": \"not_assessed\"", "\"peak_validity\": \"valid\"", "sidecar_invalid"},
			{"v0 schema", "motioncorr-quality-prototype/1", "motioncorr-quality-prototype/0", "sidecar_invalid"},
			{"foreign schema", "motioncorr-quality-prototype/1", "something-else/1", "sidecar_invalid"},
			{"missing global state", "\"global_alignment\": {\"state\": \"converged\", ", "\"global_alignment\": {", "sidecar_invalid"},
			{"bytes as string", "\"bytes\": 11", "\"bytes\": \"11\"", "sidecar_invalid"},
			{"retained with a reason", "\"state\": \"retained\", \"reason\": null", "\"state\": \"retained\", \"reason\": \"too_few_converged_observations\"", "sidecar_invalid"},
			{"global_only without reason", "\"state\": \"retained\", \"reason\": null", "\"state\": \"global_only\", \"reason\": null", "sidecar_invalid"},
			{"counts inconsistent", "\"dropped_patches\": 1", "\"dropped_patches\": 2", "sidecar_invalid"},
			{"published with a reason", "\"state\": \"published\", \"reason\": null", "\"state\": \"published\", \"reason\": \"movie_error\"", "sidecar_invalid"},
			{"not JSON", "{\n  \"schema\"", "{{\n  \"schema\"", "sidecar_invalid"},
			{"valid but failed", "\"state\": \"published\", \"reason\": null", "\"state\": \"failed\", \"reason\": \"movie_error\"", "sidecar_stale"},
		};
		for (const Case &c : cases) {
			spit(good, replaced(base, c.from, c.to));
			SummaryEntry e;
			readResumedSidecar(good, movie, star, mic, e);
			expect(e.source == "unknown_legacy" && e.reason == c.reason, std::string("U3 ") + c.name + " -> " + c.reason);
		}
		spit(good, replaced(base, sha256File(star), std::string(64, '0')));
		SummaryEntry digest;
		readResumedSidecar(good, movie, star, mic, digest);
		expect(digest.source == "unknown_legacy" && digest.reason == "sidecar_stale", "U3 recorded STAR digest differs -> sidecar_stale");
		spit(good, base);
		spit(star, "star-bytes-changed");
		SummaryEntry stale;
		readResumedSidecar(good, movie, star, mic, stale);
		expect(stale.source == "unknown_legacy" && stale.reason == "sidecar_stale", "U3 changed STAR -> sidecar_stale");
		spit(star, "star-bytes");
		std::remove(good.c_str());
		SummaryEntry missing;
		readResumedSidecar(good, movie, star, mic, missing);
		expect(missing.reason == "sidecar_missing", "U3 missing -> sidecar_missing");
	}

	// U4: unknown values are null, not placeholders.
	{
		MovieQuality q;  // failed before global alignment
		q.processed = true;
		const std::string path = dir + "/u4.json";
		expect(writeSidecar(path, id, dir + "/does-not-exist.mrcs", q, star, mic, error), "U4 sidecar written");
		const std::string text = slurp(path);
		expect(contains(text, "\"bytes\": null") && contains(text, "\"state\": \"not_assessed\", \"route\": \"none\", "
		       "\"iterations\": null, \"final_incremental_rmsd_px\": null, \"converged\": null, \"max_iter\": null, \"tolerance_px\": null"),
		       "U4 not_assessed movie has null bytes and solver fields");
		expect(contains(text, "\"min_observations_exclusive\": null") && contains(text, "\"distortion_limit_px\": null") &&
		       contains(text, "\"fit_rmsd_limit_px\": null"), "U4 unreached limits are null");
		MovieQuality not_run = healthy();
		not_run.global_solve = SolveRecord();
		not_run.global_solve.noted = true; not_run.global_solve.max_iter = 0; not_run.global_solve.tolerance_px = 0.5;
		writeSidecar(path, id, movie, not_run, star, mic, error);
		expect(contains(slurp(path), "\"state\": \"not_run\", \"route\": \"cpu\", \"iterations\": 0, "
		       "\"final_incremental_rmsd_px\": null, \"converged\": null, \"max_iter\": 0, \"tolerance_px\": 0.5"),
		       "U4 not_run keeps the reported max_iter and tolerance");
	}

	std::cout << (failures ? "FAILED " : "ALL PASSED ") << failures << std::endl;
	return failures ? 1 : 0;
}
