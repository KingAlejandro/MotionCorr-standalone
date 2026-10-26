/***************************************************************************
 * Experimental per-movie alignment quality report (issue #268 prototype).
 * See quality_report.h.
 *
 * This file is part of MotionCorr, distributed under the GNU General Public
 * License version 2 or later. See LICENSE.
 ***************************************************************************/
#include "src/quality_report.h"

#ifdef MC_EXPERIMENTAL_QUALITY_REPORT

#include <cctype>
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

const char *SIDECAR_SCHEMA = "motioncorr-quality-prototype/1";
const char *SUMMARY_SCHEMA = "motioncorr-quality-summary-prototype/1";

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

std::string nullableText(const std::string &s) { return s.empty() ? "null" : jsonText(s); }

std::string identityJson(const RunIdentity &id, const std::string &indent)
{
	std::ostringstream o;
	o << "{\n" << indent << "  \"run_id\": " << jsonText(id.run_id) << ",\n"
	  << indent << "  \"configured_source_revision\": " << jsonText(id.source_revision) << ",\n"
	  << indent << "  \"configured_source_dirty\": " << jsonText(id.source_dirty) << ",\n"
	  << indent << "  \"binary_sha256\": " << jsonText(id.binary_sha256) << ",\n"
	  << indent << "  \"backend\": " << jsonText(id.backend) << ",\n"
	  << indent << "  \"gpu_id\": " << id.gpu_id << ",\n"
	  << indent << "  \"options\": {";
	for (size_t i = 0; i < id.options.size(); i++)
		o << (i ? ", " : "") << jsonText(id.options[i].first) << ": " << jsonText(id.options[i].second);
	o << "},\n" << indent << "  \"argv\": [";
	for (size_t i = 0; i < id.argv.size(); i++) o << (i ? ", " : "") << jsonText(id.argv[i]);
	o << "]\n" << indent << "}";
	return o.str();
}

// Unknown (no solver reported) is null throughout; not_run keeps what was reported.
std::string solveJson(const SolveRecord &s)
{
	std::ostringstream o;
	o << "\"iterations\": " << (s.noted ? std::to_string(s.iterations) : "null")
	  << ", \"final_incremental_rmsd_px\": " << (s.ran ? number(s.final_rmsd_px) : "null")
	  << ", \"converged\": " << (s.ran ? (s.converged ? "true" : "false") : "null")
	  << ", \"max_iter\": " << (s.noted ? std::to_string(s.max_iter) : "null")
	  << ", \"tolerance_px\": " << (s.noted ? number(s.tolerance_px) : "null");
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

// Text written by jsonText(): a string, or the labelled hex-bytes object.
bool textAt(const Json *j, std::string &out)
{
	if (!j) return false;
	if (j->kind == Json::String) { out = j->s; return true; }
	if (j->kind != Json::Object || j->fields.size() != 1) return false;
	const Json *hex = j->get("non_utf8_bytes_hex");
	if (!hex || hex->kind != Json::String || hex->s.size() % 2) return false;
	out.clear();
	for (size_t i = 0; i < hex->s.size(); i += 2) {
		const char pair[3] = {hex->s[i], hex->s[i + 1], 0};
		if (!std::isxdigit((unsigned char)pair[0]) || !std::isxdigit((unsigned char)pair[1])) return false;
		out += (char)std::strtoul(pair, nullptr, 16);
	}
	return true;
}

bool isInteger(const Json *j, bool allow_null)
{
	if (!j) return false;
	if (j->kind == Json::Null) return allow_null;
	return j->kind == Json::Number && std::isfinite(j->n) && j->n == std::floor(j->n) && j->n >= 0;
}

bool isHexDigest(const Json *j, bool allow_null)
{
	if (!j) return false;
	if (j->kind == Json::Null) return allow_null;
	if (j->kind != Json::String || j->s.size() != 64) return false;
	for (const char c : j->s) if (!std::isxdigit((unsigned char)c)) return false;
	return true;
}

bool oneOf(const Json *j, std::initializer_list<const char *> words)
{
	if (!j || j->kind != Json::String) return false;
	for (const char *w : words) if (j->s == w) return true;
	return false;
}

// Every schema, type, vocabulary and always-not-assessed rule a v1 sidecar must
// meet before any of its content is trusted (DESIGN_V2.md, F2).
bool validSidecar(const Json &root)
{
	if (root.kind != Json::Object || !oneOf(root.get("schema"), {SIDECAR_SCHEMA}) ||
	    !oneOf(root.get("status"), {"experimental_unapproved"})) return false;
	std::string text;
	const Json *movie = root.get("movie");
	if (!movie || !textAt(movie->get("path"), text) || !isInteger(movie->get("bytes"), true) ||
	    !isHexDigest(movie->get("sha256"), true)) return false;
	const Json *g = root.get("global_alignment");
	if (!g || !oneOf(g->get("state"), {"converged", "iteration_limit", "not_run", "operator_error", "not_assessed"}) ||
	    !oneOf(g->get("route"), {"none", "cpu", "cuda_resident", "cuda_streaming"}) ||
	    !isInteger(g->get("iterations"), true)) return false;
	const Json *l = root.get("local_alignment");
	if (!l || !oneOf(l->get("state"), {"attempted", "interrupted", "not_requested", "not_assessed"})) return false;
	for (const char *k : {"patches_planned", "patches_recorded", "solver_attempts", "same_input_retries",
	                      "device_preparation_declined", "converged_patches", "dropped_patches", "interrupted_patches"})
		if (!isInteger(l->get(k), false)) return false;
	const Json *patches = l->get("patches");
	if (!patches || patches->kind != Json::Array ||
	    (double)patches->items.size() != l->get("patches_recorded")->n ||
	    l->get("converged_patches")->n + l->get("dropped_patches")->n + l->get("interrupted_patches")->n !=
	        l->get("patches_recorded")->n) return false;
	const Json *m = root.get("local_model");
	if (!m) return false;
	const Json *reason = m->get("reason");
	if (oneOf(m->get("state"), {"retained", "not_assessed"})) {
		if (!reason || reason->kind != Json::Null) return false;
	} else if (oneOf(m->get("state"), {"global_only"})) {
		if (!oneOf(reason, {"too_few_converged_observations", "distortion_guard_rejected", "fit_rmsd_above_threshold"})) return false;
	} else if (oneOf(m->get("state"), {"not_requested"})) {
		if (!oneOf(reason, {"patch_grid_below_3x3"})) return false;
	} else return false;
	if (!oneOf(root.get("motion_identifiability"), {"not_assessed"}) ||
	    !oneOf(root.get("peak_validity"), {"not_assessed"})) return false;
	const Json *pub = root.get("publication");
	if (!pub) return false;
	const Json *pub_reason = pub->get("reason");
	if (oneOf(pub->get("state"), {"published"})) {
		if (!pub_reason || pub_reason->kind != Json::Null) return false;
	} else if (oneOf(pub->get("state"), {"failed"})) {
		if (!oneOf(pub_reason, {"movie_error", "product_write_failed"})) return false;
	} else return false;
	const Json *products = root.get("products");
	if (!products || products->kind != Json::Object) return false;
	for (const char *k : {"star", "micrograph"}) {
		const Json *p = products->get(k);
		if (!p) return false;
		if (p->kind == Json::Null) continue;
		if (!textAt(p->get("path"), text) || !isHexDigest(p->get("sha256"), true)) return false;
	}
	return true;
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

bool wellFormedUtf8(const std::string &text)
{
	const unsigned char *p = reinterpret_cast<const unsigned char *>(text.data());
	const size_t n = text.size();
	for (size_t i = 0; i < n;) {
		const unsigned char c = p[i];
		size_t len; uint32_t cp;
		if (c < 0x80) { i++; continue; }
		else if (c >= 0xC2 && c <= 0xDF) { len = 2; cp = c & 0x1F; }
		else if (c >= 0xE0 && c <= 0xEF) { len = 3; cp = c & 0x0F; }
		else if (c >= 0xF0 && c <= 0xF4) { len = 4; cp = c & 0x07; }
		else return false;
		if (i + len > n) return false;
		for (size_t k = 1; k < len; k++) {
			if ((p[i + k] & 0xC0) != 0x80) return false;
			cp = (cp << 6) | (p[i + k] & 0x3F);
		}
		// Overlong forms, surrogates and values past U+10FFFF are ill-formed.
		if ((len == 3 && cp < 0x800) || (len == 4 && (cp < 0x10000 || cp > 0x10FFFF)) ||
		    (cp >= 0xD800 && cp <= 0xDFFF)) return false;
		i += len;
	}
	return true;
}

std::string jsonText(const std::string &text)
{
	if (wellFormedUtf8(text)) return quote(text);
	std::string hex;
	char buf[3];
	for (const unsigned char c : text) { std::snprintf(buf, sizeof(buf), "%02x", c); hex += buf; }
	return "{\"non_utf8_bytes_hex\": \"" + hex + "\"}";
}

bool writeSidecar(const std::string &path, const RunIdentity &id, const std::string &movie,
                  const MovieQuality &q, const std::string &star_path,
                  const std::string &micrograph_path, std::string &error)
{
	const std::string publication = publicationState(q);
	const bool published = publication == "published";
	int attempts = 0, retries = 0, declined = 0, converged = 0, dropped = 0, interrupted = 0;
	for (const PatchRecord &p : q.patches) {
		attempts += (int)p.attempts.size();
		for (const Attempt &a : p.attempts) retries += a.kind == "same_input_retry";
		declined += p.device_preparation_declined;
		if (!p.completed) interrupted++;
		else if (p.converged) converged++;
		else dropped++;
	}
	std::string local_state = q.local_state;
	if (local_state == "attempted" && (interrupted > 0 || (int)q.patches.size() < q.patches_planned))
		local_state = "interrupted";
	const long long bytes = fileSize(movie);
	auto optional_int = [](int v) { return v >= 0 ? std::to_string(v) : std::string("null"); };

	std::ostringstream o;
	o << "{\n  \"schema\": " << quote(SIDECAR_SCHEMA) << ",\n"
	  << "  \"status\": \"experimental_unapproved\",\n"
	  << "  \"identity\": " << identityJson(id, "  ") << ",\n"
	  << "  \"movie\": {\"path\": " << jsonText(movie) << ", \"bytes\": "
	  << (bytes >= 0 ? std::to_string(bytes) : "null")
	  << ", \"sha256\": " << nullableText(sha256File(movie)) << "},\n"
	  << "  \"products\": {\"star\": ";
	if (published)
		o << "{\"path\": " << jsonText(star_path) << ", \"sha256\": " << nullableText(sha256File(star_path)) << "}"
		  << ", \"micrograph\": {\"path\": " << jsonText(micrograph_path) << ", \"sha256\": "
		  << nullableText(sha256File(micrograph_path)) << "}";
	else
		o << "null, \"micrograph\": null";
	o << "},\n"
	  << "  \"global_alignment\": {\"state\": " << quote(globalState(q)) << ", \"route\": " << quote(q.global_route)
	  << ", " << solveJson(q.global_solve) << ", \"solver_returned\": "
	  << (q.global_finished ? (q.global_returned ? "true" : "false") : "null") << "},\n"
	  << "  \"local_alignment\": {\"state\": " << quote(local_state)
	  << ", \"patches_planned\": " << q.patches_planned
	  << ", \"patches_recorded\": " << q.patches.size()
	  << ", \"solver_attempts\": " << attempts
	  << ", \"same_input_retries\": " << retries
	  << ", \"device_preparation_declined\": " << declined
	  << ", \"converged_patches\": " << converged
	  << ", \"dropped_patches\": " << dropped
	  << ", \"interrupted_patches\": " << interrupted
	  << ",\n    \"patches\": [";
	for (size_t i = 0; i < q.patches.size(); i++) {
		const PatchRecord &p = q.patches[i];
		o << (i ? "," : "") << "\n      {\"index\": " << p.index << ", \"iy\": " << p.iy << ", \"ix\": " << p.ix
		  << ", \"final\": " << quote(!p.completed ? "interrupted" : p.converged ? "converged" : "dropped")
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
	  << "  \"local_model\": {\"state\": " << quote(q.model_state) << ", \"reason\": "
	  << (q.model_reason.empty() ? "null" : quote(q.model_reason))
	  << ", \"observations\": " << optional_int(q.observations)
	  << ", \"min_observations_exclusive\": " << optional_int(q.min_observations_exclusive)
	  << ", \"largest_delta_px\": " << number(q.largest_delta_px)
	  << ", \"distortion_limit_px\": " << number(q.distortion_limit_px)
	  << ", \"fit_rmsd_x_px\": " << number(q.fit_rmsd_x_px) << ", \"fit_rmsd_y_px\": " << number(q.fit_rmsd_y_px)
	  << ", \"fit_rmsd_limit_px\": " << number(q.fit_rmsd_limit_px) << "},\n"
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
	entry.publication_state = "complete_prior_run";  // the unchanged completion check passed
	struct stat st;
	if (::stat(path.c_str(), &st) != 0) { entry.reason = "sidecar_missing"; return; }
	std::ifstream in(path.c_str(), std::ios::binary);
	std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
	Json root;
	Parser parser(text);
	if (!S_ISREG(st.st_mode) || in.bad() || !parser.document(root) || !validSidecar(root)) {
		entry.reason = "sidecar_invalid";
		return;
	}
	entry.sidecar_sha256 = sha256File(path);
	std::string recorded_movie, recorded_star, recorded_mic;
	const Json *bytes = root.path({"movie", "bytes"});
	const long long current_bytes = fileSize(movie);
	const std::string star_hash = sha256File(star_path), mic_hash = sha256File(micrograph_path);
	const bool bound =
		textAt(root.path({"movie", "path"}), recorded_movie) && recorded_movie == movie &&
		bytes->kind == Json::Number && current_bytes >= 0 && (long long)bytes->n == current_bytes &&
		stringAt(root, {"publication", "state"}) == "published" &&
		textAt(root.path({"products", "star", "path"}), recorded_star) && recorded_star == star_path &&
		textAt(root.path({"products", "micrograph", "path"}), recorded_mic) && recorded_mic == micrograph_path &&
		!star_hash.empty() && stringAt(root, {"products", "star", "sha256"}) == star_hash &&
		!mic_hash.empty() && stringAt(root, {"products", "micrograph", "sha256"}) == mic_hash;
	if (!bound) { entry.reason = "sidecar_stale"; return; }
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
	// Global/local-model counts cover entries whose states are known; publication
	// counts cover every entry.
	std::map<std::string, int> global, model, publication;
	int legacy = 0, write_failures = 0, collisions = 0;
	for (const SummaryEntry &e : entries) {
		publication[e.publication_state]++;
		collisions += e.output_root_collision;
		write_failures += e.sidecar_write_failed;
		if (e.source == "unknown_legacy") { legacy++; continue; }
		global[e.global_state]++;
		model[e.local_model_state]++;
	}
	auto counts = [](const std::map<std::string, int> &m) {
		std::ostringstream o; o << "{";
		bool first = true;
		for (const auto &kv : m) { o << (first ? "" : ", ") << jsonText(kv.first) << ": " << kv.second; first = false; }
		return o.str() + "}";
	};

	std::ostringstream o;
	o << "{\n  \"schema\": " << quote(SUMMARY_SCHEMA) << ",\n"
	  << "  \"status\": \"experimental_unapproved\",\n"
	  << "  \"identity\": " << identityJson(id, "  ") << ",\n"
	  << "  \"joint_output\": {\"state\": " << quote(joint_state) << ", \"path\": " << jsonText(joint_path) << "},\n"
	  << "  \"quality_evidence_complete\": "
	  << ((legacy == 0 && write_failures == 0 && collisions == 0) ? "true" : "false") << ",\n"
	  << "  \"counts\": {\"movies\": " << entries.size() << ", \"unknown_legacy\": " << legacy
	  << ", \"sidecar_write_failures\": " << write_failures << ", \"output_root_collisions\": " << collisions
	  << ", \"global_alignment\": " << counts(global) << ", \"local_model\": " << counts(model)
	  << ", \"publication\": " << counts(publication) << "},\n"
	  << "  \"movies\": [";
	for (size_t i = 0; i < entries.size(); i++) {
		const SummaryEntry &e = entries[i];
		const bool legacy_entry = e.source == "unknown_legacy";
		o << (i ? "," : "") << "\n    {\"movie\": " << jsonText(e.movie) << ", \"source\": " << quote(e.source)
		  << ", \"reason\": " << (e.reason.empty() ? "null" : quote(e.reason))
		  << ", \"output_root_collision\": " << (e.output_root_collision ? "true" : "false")
		  << ", \"sidecar\": {\"path\": " << nullableText(e.sidecar_path) << ", \"sha256\": " << nullableText(e.sidecar_sha256)
		  << ", \"write_failed\": " << (e.sidecar_write_failed ? "true" : "false")
		  << ", \"write_error\": " << nullableText(e.sidecar_write_error) << "}"
		  << ", \"global_alignment\": " << (legacy_entry ? "\"unknown_legacy\"" : quote(e.global_state))
		  << ", \"local_model\": " << (legacy_entry ? "\"unknown_legacy\"" : quote(e.local_model_state))
		  << ", \"publication\": " << quote(e.publication_state) << "}";
	}
	o << (entries.empty() ? "" : "\n  ") << "]\n}\n";
	return atomicWrite(path, o.str(), error);
}

}  // namespace mcquality

#endif  // MC_EXPERIMENTAL_QUALITY_REPORT
