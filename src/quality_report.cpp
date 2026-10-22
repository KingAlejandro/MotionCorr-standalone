/***************************************************************************
 * Experimental per-movie alignment quality report (issue #268 prototype).
 * See quality_report.h.
 *
 * This file is part of MotionCorr, distributed under the GNU General Public
 * License version 2 or later. See LICENSE.
 ***************************************************************************/
#include "src/quality_report.h"

#ifdef MC_EXPERIMENTAL_QUALITY_REPORT

#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <memory>
#include <random>
#include <sstream>
#include <sys/stat.h>
#include <unistd.h>

namespace mcquality {

thread_local SolveRecord *active_solve = nullptr;

namespace {

const char *SIDECAR_SCHEMA = "motioncorr-quality-prototype/0";
const char *SUMMARY_SCHEMA = "motioncorr-quality-summary-prototype/0";

// ---- SHA-256 (FIPS 180-4) ----
struct Sha256
{
	uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
	                 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
	unsigned char block[64];
	size_t fill = 0;
	uint64_t bytes = 0;

	static uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

	void compress(const unsigned char *p)
	{
		static const uint32_t k[64] = {
			0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
			0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
			0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
			0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
			0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
			0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
			0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
			0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
		uint32_t w[64];
		for (int i = 0; i < 16; i++)
			w[i] = (uint32_t)p[4*i] << 24 | (uint32_t)p[4*i+1] << 16 | (uint32_t)p[4*i+2] << 8 | p[4*i+3];
		for (int i = 16; i < 64; i++) {
			const uint32_t s0 = rotr(w[i-15], 7) ^ rotr(w[i-15], 18) ^ (w[i-15] >> 3);
			const uint32_t s1 = rotr(w[i-2], 17) ^ rotr(w[i-2], 19) ^ (w[i-2] >> 10);
			w[i] = w[i-16] + s0 + w[i-7] + s1;
		}
		uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
		for (int i = 0; i < 64; i++) {
			const uint32_t t1 = hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + k[i] + w[i];
			const uint32_t t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
			hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
		}
		h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
	}

	void update(const unsigned char *p, size_t n)
	{
		bytes += n;
		while (n > 0) {
			const size_t take = std::min(n, sizeof(block) - fill);
			std::memcpy(block + fill, p, take);
			fill += take; p += take; n -= take;
			if (fill == sizeof(block)) { compress(block); fill = 0; }
		}
	}

	std::string hex()
	{
		const uint64_t bits = bytes * 8;
		const unsigned char pad = 0x80, zero = 0;
		update(&pad, 1);
		while (fill != 56) update(&zero, 1);
		unsigned char len[8];
		for (int i = 0; i < 8; i++) len[i] = (unsigned char)(bits >> (56 - 8 * i));
		update(len, 8);
		char out[65];
		for (int i = 0; i < 8; i++) std::snprintf(out + 8 * i, 9, "%08x", h[i]);
		return std::string(out, 64);
	}
};

long long fileSize(const std::string &path)
{
	struct stat st;
	if (::stat(path.c_str(), &st) != 0 || !S_ISREG(st.st_mode)) return -1;
	return (long long)st.st_size;
}

// ---- JSON writing ----
std::string quote(const std::string &s)
{
	std::string out = "\"";
	for (const unsigned char c : s) {
		switch (c) {
		case '"': out += "\\\""; break;
		case '\\': out += "\\\\"; break;
		case '\n': out += "\\n"; break;
		case '\r': out += "\\r"; break;
		case '\t': out += "\\t"; break;
		default:
			if (c < 0x20) { char buf[8]; std::snprintf(buf, sizeof(buf), "\\u%04x", c); out += buf; }
			else out += (char)c;
		}
	}
	return out + "\"";
}

std::string number(double v)
{
	if (!std::isfinite(v)) return "null";
	char buf[32];
	std::snprintf(buf, sizeof(buf), "%.17g", v);
	return buf;
}

std::string nullableString(const std::string &s) { return s.empty() ? "null" : quote(s); }

std::string identityJson(const RunIdentity &id, const std::string &indent)
{
	std::ostringstream o;
	o << "{\n" << indent << "  \"run_id\": " << quote(id.run_id) << ",\n"
	  << indent << "  \"configured_source_revision\": " << quote(id.source_revision) << ",\n"
	  << indent << "  \"configured_source_dirty\": " << quote(id.source_dirty) << ",\n"
	  << indent << "  \"binary_sha256\": " << quote(id.binary_sha256) << ",\n"
	  << indent << "  \"backend\": " << quote(id.backend) << ",\n"
	  << indent << "  \"gpu_id\": " << id.gpu_id << ",\n"
	  << indent << "  \"options\": {";
	for (size_t i = 0; i < id.options.size(); i++)
		o << (i ? ", " : "") << quote(id.options[i].first) << ": " << quote(id.options[i].second);
	o << "},\n" << indent << "  \"argv\": [";
	for (size_t i = 0; i < id.argv.size(); i++) o << (i ? ", " : "") << quote(id.argv[i]);
	o << "]\n" << indent << "}";
	return o.str();
}

std::string solveJson(const SolveRecord &s)
{
	std::ostringstream o;
	o << "\"iterations\": " << s.iterations << ", \"final_incremental_rmsd_px\": "
	  << (s.ran ? number(s.final_rmsd_px) : "null") << ", \"converged\": "
	  << (s.ran ? (s.converged ? "true" : "false") : "null");
	return o.str();
}

bool atomicWrite(const std::string &path, const std::string &content, std::string &error)
{
	std::ostringstream tmp_name;
	tmp_name << path << ".tmp." << ::getpid() << "." << std::random_device()();
	const std::string tmp = tmp_name.str();
	{
		std::ofstream out(tmp.c_str(), std::ios::binary | std::ios::trunc);
		if (!out) { error = "cannot create " + tmp + ": " + std::strerror(errno); return false; }
		out << content;
		out.flush();
		out.close();
		if (!out) {
			error = "write failed for " + tmp;
			std::remove(tmp.c_str());
			return false;
		}
	}
	if (std::rename(tmp.c_str(), path.c_str()) != 0) {
		error = "cannot rename " + tmp + " to " + path + ": " + std::strerror(errno);
		std::remove(tmp.c_str());
		return false;
	}
	return true;
}

// ---- Minimal JSON reading, enough to validate our own sidecar ----
struct Json
{
	enum Kind { Null, Bool, Number, String, Array, Object } kind = Null;
	bool b = false;
	double n = 0;
	std::string s;
	std::vector<Json> items;
	std::map<std::string, Json> fields;

	const Json *get(const std::string &key) const
	{
		if (kind != Object) return nullptr;
		auto it = fields.find(key);
		return it == fields.end() ? nullptr : &it->second;
	}
	const Json *path(std::initializer_list<const char *> keys) const
	{
		const Json *j = this;
		for (const char *k : keys) { j = j ? j->get(k) : nullptr; }
		return j;
	}
};

struct Parser
{
	const std::string &t;
	size_t i = 0;
	explicit Parser(const std::string &text) : t(text) {}

	void ws() { while (i < t.size() && (t[i] == ' ' || t[i] == '\n' || t[i] == '\r' || t[i] == '\t')) i++; }
	bool lit(const char *w) { const size_t n = std::strlen(w); if (t.compare(i, n, w) != 0) return false; i += n; return true; }

	bool str(std::string &out)
	{
		if (i >= t.size() || t[i] != '"') return false;
		i++;
		while (i < t.size() && t[i] != '"') {
			char c = t[i++];
			if (c == '\\') {
				if (i >= t.size()) return false;
				const char e = t[i++];
				if (e == 'n') c = '\n'; else if (e == 't') c = '\t'; else if (e == 'r') c = '\r';
				else if (e == '"' || e == '\\' || e == '/') c = e;
				else if (e == 'u' && i + 4 <= t.size()) {
					const unsigned long v = std::strtoul(t.substr(i, 4).c_str(), nullptr, 16);
					i += 4;
					if (v > 0x7f) return false;  // our writer never emits these
					c = (char)v;
				} else return false;
			}
			out += c;
		}
		if (i >= t.size()) return false;
		i++;
		return true;
	}

	bool value(Json &v, int depth)
	{
		if (depth > 32) return false;
		ws();
		if (i >= t.size()) return false;
		if (t[i] == '{') {
			v.kind = Json::Object; i++; ws();
			if (i < t.size() && t[i] == '}') { i++; return true; }
			while (true) {
				ws(); std::string key;
				if (!str(key)) return false;
				ws(); if (i >= t.size() || t[i] != ':') return false; i++;
				Json child; if (!value(child, depth + 1)) return false;
				if (v.fields.count(key)) return false;
				v.fields[key] = std::move(child);
				ws(); if (i < t.size() && t[i] == ',') { i++; continue; }
				if (i < t.size() && t[i] == '}') { i++; return true; }
				return false;
			}
		}
		if (t[i] == '[') {
			v.kind = Json::Array; i++; ws();
			if (i < t.size() && t[i] == ']') { i++; return true; }
			while (true) {
				Json child; if (!value(child, depth + 1)) return false;
				v.items.push_back(std::move(child));
				ws(); if (i < t.size() && t[i] == ',') { i++; continue; }
				if (i < t.size() && t[i] == ']') { i++; return true; }
				return false;
			}
		}
		if (t[i] == '"') { v.kind = Json::String; return str(v.s); }
		if (lit("true")) { v.kind = Json::Bool; v.b = true; return true; }
		if (lit("false")) { v.kind = Json::Bool; v.b = false; return true; }
		if (lit("null")) { v.kind = Json::Null; return true; }
		char *end = nullptr;
		v.n = std::strtod(t.c_str() + i, &end);
		if (end == t.c_str() + i) return false;
		v.kind = Json::Number; i = end - t.c_str();
		return true;
	}

	bool document(Json &v) { if (!value(v, 0)) return false; ws(); return i == t.size(); }
};

std::string stringAt(const Json &root, std::initializer_list<const char *> keys)
{
	const Json *j = root.path(keys);
	return (j && j->kind == Json::String) ? j->s : std::string();
}

}  // namespace

std::string makeRunId()
{
	const auto now = std::chrono::system_clock::now().time_since_epoch();
	std::ostringstream o;
	o << std::chrono::duration_cast<std::chrono::microseconds>(now).count() << "-" << ::getpid()
	  << "-" << std::hex << std::random_device()();
	return o.str();
}

std::string sha256File(const std::string &path)
{
	std::ifstream in(path.c_str(), std::ios::binary);
	if (!in) return "";
	Sha256 hash;
	std::vector<char> buf(1 << 20);
	while (in) {
		in.read(buf.data(), buf.size());
		const std::streamsize got = in.gcount();
		if (got > 0) hash.update(reinterpret_cast<const unsigned char *>(buf.data()), (size_t)got);
	}
	if (in.bad()) return "";
	return hash.hex();
}

std::string selfBinarySha256()
{
	const std::string hash = sha256File("/proc/self/exe");
	return hash.empty() ? "unavailable" : hash;
}

std::string globalState(const MovieQuality &q)
{
	if (!q.global_started) return "not_assessed";
	if (!q.global_finished) return "operator_error";
	if (!q.global_solve.ran) return "not_run";
	return q.global_solve.converged ? "converged" : "iteration_limit";
}

std::string publicationState(const MovieQuality &q)
{
	return (q.computation_ok && !q.write_failed) ? "published" : "failed";
}

bool supersede(const std::string &path, const std::string &run_id, std::string &error)
{
	struct stat st;
	if (::lstat(path.c_str(), &st) != 0 || !S_ISREG(st.st_mode)) return true;
	const size_t dot = path.rfind(".json");
	const std::string target = (dot == std::string::npos ? path : path.substr(0, dot))
		+ ".superseded-" + run_id + ".json";
	if (std::rename(path.c_str(), target.c_str()) != 0) {
		error = "cannot supersede " + path + ": " + std::strerror(errno);
		return false;
	}
	return true;
}

bool writeSidecar(const std::string &path, const RunIdentity &id, const std::string &movie,
                  const MovieQuality &q, const std::string &star_path,
                  const std::string &micrograph_path, std::string &error)
{
	const std::string publication = publicationState(q);
	const bool published = publication == "published";
	int attempts = 0, retries = 0, declined = 0, converged = 0;
	for (const PatchRecord &p : q.patches) {
		attempts += (int)p.attempts.size();
		for (const Attempt &a : p.attempts) retries += a.kind == "same_input_retry";
		declined += p.device_preparation_declined;
		converged += p.converged;
	}

	std::ostringstream o;
	o << "{\n  \"schema\": " << quote(SIDECAR_SCHEMA) << ",\n"
	  << "  \"status\": \"experimental_unapproved\",\n"
	  << "  \"identity\": " << identityJson(id, "  ") << ",\n"
	  << "  \"movie\": {\"path\": " << quote(movie) << ", \"bytes\": " << fileSize(movie)
	  << ", \"sha256\": " << nullableString(sha256File(movie)) << "},\n"
	  << "  \"products\": {\"star\": ";
	if (published)
		o << "{\"path\": " << quote(star_path) << ", \"sha256\": " << nullableString(sha256File(star_path)) << "}"
		  << ", \"micrograph\": {\"path\": " << quote(micrograph_path) << ", \"sha256\": "
		  << nullableString(sha256File(micrograph_path)) << "}";
	else
		o << "null, \"micrograph\": null";
	o << "},\n"
	  << "  \"global_alignment\": {\"state\": " << quote(globalState(q)) << ", \"route\": " << quote(q.global_route)
	  << ", " << solveJson(q.global_solve) << ", \"max_iter\": " << q.global_solve.max_iter
	  << ", \"tolerance_px\": " << number(q.global_solve.tolerance_px) << ", \"solver_returned\": "
	  << (q.global_finished ? (q.global_returned ? "true" : "false") : "null") << "},\n"
	  << "  \"local_alignment\": {\"state\": " << quote(q.local_state)
	  << ", \"patches_planned\": " << q.patches_planned
	  << ", \"patches_recorded\": " << q.patches.size()
	  << ", \"solver_attempts\": " << attempts
	  << ", \"same_input_retries\": " << retries
	  << ", \"device_preparation_declined\": " << declined
	  << ", \"converged_patches\": " << converged
	  << ", \"dropped_patches\": " << (int)q.patches.size() - converged
	  << ",\n    \"patches\": [";
	for (size_t i = 0; i < q.patches.size(); i++) {
		const PatchRecord &p = q.patches[i];
		o << (i ? "," : "") << "\n      {\"index\": " << p.index << ", \"iy\": " << p.iy << ", \"ix\": " << p.ix
		  << ", \"final\": " << quote(p.converged ? "converged" : "dropped")
		  << ", \"device_preparation_declined\": " << (p.device_preparation_declined ? "true" : "false")
		  << ", \"attempts\": [";
		for (size_t k = 0; k < p.attempts.size(); k++) {
			const Attempt &a = p.attempts[k];
			o << (k ? ", " : "") << "{\"route\": " << quote(a.route) << ", \"kind\": " << quote(a.kind)
			  << ", " << solveJson(a.solve) << ", \"solver_returned\": " << (a.solver_returned ? "true" : "false") << "}";
		}
		o << "]}";
	}
	o << (q.patches.empty() ? "" : "\n    ") << "]},\n"
	  << "  \"local_model\": {\"state\": " << quote(q.model_state) << ", \"reason\": " << nullableString(q.model_reason)
	  << ", \"observations\": " << (q.observations >= 0 ? std::to_string(q.observations) : "null")
	  << ", \"min_observations_exclusive\": 18"
	  << ", \"largest_delta_px\": " << number(q.largest_delta_px) << ", \"distortion_limit_px\": 3"
	  << ", \"fit_rmsd_x_px\": " << number(q.fit_rmsd_x_px) << ", \"fit_rmsd_y_px\": " << number(q.fit_rmsd_y_px)
	  << ", \"fit_rmsd_limit_px\": 10},\n"
	  << "  \"motion_identifiability\": \"not_assessed\",\n"
	  << "  \"peak_validity\": \"not_assessed\",\n"
	  << "  \"publication\": {\"state\": " << quote(publication) << ", \"reason\": "
	  << (published ? "null" : quote(q.computation_ok ? "product_write_failed" : "movie_error")) << "}\n}\n";
	return atomicWrite(path, o.str(), error);
}

void readResumedSidecar(const std::string &path, const std::string &movie,
                        const std::string &star_path, const std::string &micrograph_path,
                        SummaryEntry &entry)
{
	entry.movie = movie;
	entry.sidecar_path = path;
	entry.source = "unknown_legacy";
	struct stat st;
	if (::stat(path.c_str(), &st) != 0) { entry.reason = "sidecar_missing"; return; }
	std::ifstream in(path.c_str(), std::ios::binary);
	std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
	Json root;
	Parser parser(text);
	if (!in.good() && !in.eof()) { entry.reason = "sidecar_invalid"; return; }
	if (!S_ISREG(st.st_mode) || !parser.document(root) || root.kind != Json::Object ||
	    stringAt(root, {"schema"}) != SIDECAR_SCHEMA) { entry.reason = "sidecar_invalid"; return; }
	entry.sidecar_sha256 = sha256File(path);
	const Json *bytes = root.path({"movie", "bytes"});
	const std::string star_hash = sha256File(star_path), mic_hash = sha256File(micrograph_path);
	if (stringAt(root, {"movie", "path"}) != movie || !bytes || bytes->kind != Json::Number ||
	    (long long)bytes->n != fileSize(movie) ||
	    stringAt(root, {"publication", "state"}) != "published" ||
	    stringAt(root, {"products", "star", "path"}) != star_path ||
	    stringAt(root, {"products", "micrograph", "path"}) != micrograph_path ||
	    star_hash.empty() || stringAt(root, {"products", "star", "sha256"}) != star_hash ||
	    mic_hash.empty() || stringAt(root, {"products", "micrograph", "sha256"}) != mic_hash) {
		entry.reason = "sidecar_stale";
		return;
	}
	entry.source = "resumed_sidecar";
	entry.global_state = stringAt(root, {"global_alignment", "state"});
	entry.local_model_state = stringAt(root, {"local_model", "state"});
	entry.publication_state = "published";
}

bool writeSummary(const std::string &path, const RunIdentity &id,
                  const std::vector<SummaryEntry> &entries,
                  const std::string &joint_state, const std::string &joint_path,
                  std::string &error)
{
	std::map<std::string, int> global, model, publication;
	int legacy = 0, write_failures = 0;
	for (const SummaryEntry &e : entries) {
		if (e.source == "unknown_legacy") { legacy++; continue; }
		global[e.global_state]++;
		model[e.local_model_state]++;
		publication[e.publication_state]++;
		write_failures += e.sidecar_write_failed;
	}
	auto counts = [](const std::map<std::string, int> &m) {
		std::ostringstream o; o << "{";
		bool first = true;
		for (const auto &kv : m) { o << (first ? "" : ", ") << quote(kv.first) << ": " << kv.second; first = false; }
		return o.str() + "}";
	};

	std::ostringstream o;
	o << "{\n  \"schema\": " << quote(SUMMARY_SCHEMA) << ",\n"
	  << "  \"status\": \"experimental_unapproved\",\n"
	  << "  \"identity\": " << identityJson(id, "  ") << ",\n"
	  << "  \"joint_output\": {\"state\": " << quote(joint_state) << ", \"path\": " << quote(joint_path) << "},\n"
	  << "  \"quality_evidence_complete\": " << ((legacy == 0 && write_failures == 0) ? "true" : "false") << ",\n"
	  << "  \"counts\": {\"movies\": " << entries.size() << ", \"unknown_legacy\": " << legacy
	  << ", \"sidecar_write_failures\": " << write_failures
	  << ", \"global_alignment\": " << counts(global) << ", \"local_model\": " << counts(model)
	  << ", \"publication\": " << counts(publication) << "},\n"
	  << "  \"movies\": [";
	for (size_t i = 0; i < entries.size(); i++) {
		const SummaryEntry &e = entries[i];
		const bool legacy_entry = e.source == "unknown_legacy";
		o << (i ? "," : "") << "\n    {\"movie\": " << quote(e.movie) << ", \"source\": " << quote(e.source)
		  << ", \"reason\": " << nullableString(e.reason)
		  << ", \"sidecar\": {\"path\": " << quote(e.sidecar_path) << ", \"sha256\": " << nullableString(e.sidecar_sha256)
		  << ", \"write_failed\": " << (e.sidecar_write_failed ? "true" : "false")
		  << ", \"write_error\": " << nullableString(e.sidecar_write_error) << "}"
		  << ", \"global_alignment\": " << (legacy_entry ? "\"unknown_legacy\"" : quote(e.global_state))
		  << ", \"local_model\": " << (legacy_entry ? "\"unknown_legacy\"" : quote(e.local_model_state))
		  // A skipped movie passed the unchanged resume completion check.
		  << ", \"publication\": " << (legacy_entry ? "\"complete_prior_run\"" : quote(e.publication_state)) << "}";
	}
	o << (entries.empty() ? "" : "\n  ") << "]\n}\n";
	return atomicWrite(path, o.str(), error);
}

}  // namespace mcquality

#endif  // MC_EXPERIMENTAL_QUALITY_REPORT
