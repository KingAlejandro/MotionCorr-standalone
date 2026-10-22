/*
 * MotionCorr #265 native round-trip oracle for the local motion model STAR table.
 * Copyright (C) 2026 MotionCorr contributors
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Calls the real ThirdOrderPolynomialModel::getShiftAt, ::write and ::read (and
 * through them the real MetaDataTable formatter and parser). Nothing of the
 * formatter or parser is reimplemented here. The pre-write coefficients are the
 * constructed doubles from the frozen fixture table; they are never re-fitted
 * and never recovered from rounded STAR text.
 *
 * Usage: roundtrip_oracle <fixtures.txt> <outdir>
 * Prints a compact table on stdout; writes full detail under <outdir>.
 * Single threaded; no numeric parallelism.
 */
#include "src/micrograph_model.h"
#include "src/metadata_table.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

static const int NC = 18;
static const char *BLOCK = "local_motion_model";

struct Geometry { std::string name; double w, h; };
struct Range { std::string name; int lo, hi; };
struct Fixture
{
	std::string name, description;
	double cx[NC], cy[NC];
};
struct Spec
{
	std::vector<Geometry> geoms;
	std::vector<double> fractions;
	std::vector<std::pair<double, double> > extra;
	int frames = 0;
	std::vector<Range> ranges;
	std::vector<Fixture> fixtures;
};

static Spec loadSpec(const std::string &path)
{
	std::ifstream in(path);
	if (!in) throw std::runtime_error("cannot open " + path);
	Spec s;
	std::string line;
	int pending = 0; // 0 none, 1 expecting X, 2 expecting Y
	while (std::getline(in, line))
	{
		if (line.empty() || line[0] == '#') continue;
		std::istringstream ls(line);
		std::string tag;
		ls >> tag;
		if (tag == "GEOMETRY") { Geometry g; ls >> g.name >> g.w >> g.h; s.geoms.push_back(g); }
		else if (tag == "FRACTIONS") { double f; while (ls >> f) s.fractions.push_back(f); }
		else if (tag == "EXTRA_PIXEL") { double a, b; ls >> a >> b; s.extra.push_back({a, b}); }
		else if (tag == "FRAMES") ls >> s.frames;
		else if (tag == "RANGE") { Range r; ls >> r.name >> r.lo >> r.hi; s.ranges.push_back(r); }
		else if (tag == "FIXTURE")
		{
			Fixture f;
			const size_t bar = line.find('|');
			f.name = line.substr(8, (bar == std::string::npos ? line.size() : bar) - 8);
			while (!f.name.empty() && f.name.back() == ' ') f.name.pop_back();
			f.description = bar == std::string::npos ? "" : line.substr(bar + 2);
			s.fixtures.push_back(f);
			pending = 1;
		}
		else if (tag == "X" || tag == "Y")
		{
			if (s.fixtures.empty() || pending != (tag == "X" ? 1 : 2))
				throw std::runtime_error("fixture rows out of order");
			double *dst = tag == "X" ? s.fixtures.back().cx : s.fixtures.back().cy;
			for (int i = 0; i < NC; i++)
			{
				std::string tok;
				if (!(ls >> tok)) throw std::runtime_error("short coefficient row in " + s.fixtures.back().name);
				char *end = nullptr;
				dst[i] = std::strtod(tok.c_str(), &end);
				if (*end) throw std::runtime_error("bad coefficient token " + tok);
			}
			std::string extra;
			if (ls >> extra) throw std::runtime_error("long coefficient row in " + s.fixtures.back().name);
			pending = tag == "X" ? 2 : 0;
		}
		else throw std::runtime_error("unknown line: " + line);
	}
	if (pending) throw std::runtime_error("unterminated fixture");
	if (s.geoms.empty() || s.fractions.empty() || s.frames <= 0 || s.fixtures.empty())
		throw std::runtime_error("incomplete spec");
	return s;
}

static void fillModel(ThirdOrderPolynomialModel &m, const double *cx, const double *cy)
{
	m.coeffX.resize(NC); m.coeffX.initZeros();
	m.coeffY.resize(NC); m.coeffY.initZeros();
	for (int i = 0; i < NC; i++) { m.coeffX(i) = cx[i]; m.coeffY(i) = cy[i]; }
}

static std::string slurp(const std::string &p)
{
	std::ifstream in(p, std::ios::binary);
	return std::string((std::istreambuf_iterator<char>(in)), {});
}

// The real write function, to a file; returns the exact bytes written.
static std::string realWrite(ThirdOrderPolynomialModel &m, const std::string &path)
{
	{
		std::ofstream fh(path);
		if (!fh) throw std::runtime_error("cannot create " + path);
		m.write(fh, BLOCK);
	}
	return slurp(path);
}

// The real read function. Returns false and the error text if it throws.
static bool realRead(ThirdOrderPolynomialModel &m, const std::string &path, std::string &err)
{
	std::ifstream fh(path);
	if (!fh) { err = "cannot open " + path; return false; }
	try { m.read(fh, BLOCK); }
	catch (RelionError &e) { err = e.msg; return false; }
	catch (std::exception &e) { err = e.what(); return false; }
	return true;
}

// TEST-ONLY control file: the real written text with only the coefficient token on
// each data line replaced by the %.17g rendering of the pre-write double. Data lines
// are the two-field lines "<int idx> <number>"; a column-order sanity check refuses
// any other shape rather than guessing.
static std::string fullPrecisionText(const std::string &real, const double *cx, const double *cy,
                                     int mutate_index, double mutate_delta)
{
	std::istringstream in(real);
	std::ostringstream out;
	std::string line;
	int seen = 0;
	while (std::getline(in, line))
	{
		std::istringstream ls(line);
		std::string a, b, c;
		ls >> a >> b >> c;
		char *e1 = nullptr;
		const long idx = std::strtol(a.c_str(), &e1, 10);
		if (!a.empty() && *e1 == 0 && !b.empty() && c.empty() && idx >= 0 && idx < 2 * NC)
		{
			double v = idx < NC ? cx[idx] : cy[idx - NC];
			if (idx == mutate_index) v += mutate_delta;
			char buf[64];
			std::snprintf(buf, sizeof buf, "%.17g", v);
			out << a << " " << buf << "\n";
			seen++;
		}
		else out << line << "\n";
	}
	if (seen != 2 * NC) throw std::runtime_error("full-precision rewrite saw " + std::to_string(seen) + " data lines");
	return out.str();
}

struct Sample
{
	int g; int frame; double px, py, xn, yn;
	double pre_x, pre_y, post_x, post_y, ex, ey, vec;
};

struct Agg
{
	double max_ex = 0, max_ey = 0, max_vec = 0;
	Sample at_ex{}, at_ey{}, at_vec{};
	bool any = false;
	long n = 0;
	double sum_sq = 0;
	void add(const Sample &s)
	{
		if (!any) { at_ex = at_ey = at_vec = s; any = true; }
		if (std::fabs(s.ex) > max_ex) { max_ex = std::fabs(s.ex); at_ex = s; }
		if (std::fabs(s.ey) > max_ey) { max_ey = std::fabs(s.ey); at_ey = s; }
		if (s.vec > max_vec) { max_vec = s.vec; at_vec = s; }
		n++; sum_sq += s.vec * s.vec;
	}
};

static std::string num(double v)
{
	char b[64];
	std::snprintf(b, sizeof b, "%.17g", v);
	return b;
}
static std::string jesc(const std::string &t)
{
	std::string o;
	for (char c : t)
	{
		if (c == '"' || c == '\\') { o += '\\'; o += c; }
		else if (c == '\n') o += "\\n";
		else if ((unsigned char) c < 0x20) o += ' ';
		else o += c;
	}
	return o;
}
static std::string hexf(double v)
{
	char b[64];
	std::snprintf(b, sizeof b, "%a", v);
	return b;
}

struct Result
{
	std::string fixture, route; // route: real-write / full-precision-test-only / injected
	bool read_ok = true; std::string read_err;
	int coeff_not_bit_equal = 0;
	double max_coeff_abs_err = 0, max_coeff_rel_err = 0;
	std::vector<std::vector<std::string> > coeff_rows; // csv rows
	std::vector<Agg> ranges; Agg all;
	std::vector<double> per_frame_max; // vec
	std::vector<Sample> top; // top 5 by vec
};

static std::vector<Sample> evaluate(const Spec &spec, const ThirdOrderPolynomialModel &pre,
                                    const ThirdOrderPolynomialModel &post, std::ofstream *csv,
                                    const std::string &tag, Result &r)
{
	std::vector<Sample> all;
	r.ranges.assign(spec.ranges.size(), Agg());
	r.per_frame_max.assign(spec.frames, 0.0);
	for (size_t gi = 0; gi < spec.geoms.size(); gi++)
	{
		const Geometry &g = spec.geoms[gi];
		std::vector<std::pair<double, double> > pos;
		for (double fy : spec.fractions)
			for (double fx : spec.fractions) pos.push_back({fx * (g.w - 1), fy * (g.h - 1)});
		for (auto &p : spec.extra) pos.push_back(p);
		for (auto &p : pos)
		{
			// Same normalisation as Micrograph::getShiftAt(normalise=true).
			const double xn = p.first / g.w - 0.5, yn = p.second / g.h - 0.5;
			for (int f = 0; f < spec.frames; f++)
			{
				Sample s{};
				s.g = (int) gi; s.frame = f; s.px = p.first; s.py = p.second; s.xn = xn; s.yn = yn;
				pre.getShiftAt((double) f, xn, yn, s.pre_x, s.pre_y);
				post.getShiftAt((double) f, xn, yn, s.post_x, s.post_y);
				s.ex = s.post_x - s.pre_x; s.ey = s.post_y - s.pre_y;
				s.vec = std::hypot(s.ex, s.ey);
				all.push_back(s);
				r.all.add(s);
				for (size_t k = 0; k < spec.ranges.size(); k++)
					if (f >= spec.ranges[k].lo && f <= spec.ranges[k].hi) r.ranges[k].add(s);
				r.per_frame_max[f] = std::max(r.per_frame_max[f], s.vec);
				if (csv)
					*csv << tag << "," << g.name << "," << f << "," << num(s.px) << "," << num(s.py) << ","
					     << num(xn) << "," << num(yn) << "," << num(s.pre_x) << "," << num(s.pre_y) << ","
					     << num(s.post_x) << "," << num(s.post_y) << "," << num(s.ex) << "," << num(s.ey)
					     << "," << num(s.vec) << "\n";
			}
		}
	}
	std::vector<Sample> sorted = all;
	std::stable_sort(sorted.begin(), sorted.end(), [](const Sample &a, const Sample &b) { return a.vec > b.vec; });
	if (sorted.size() > 5) sorted.resize(5);
	r.top = sorted;
	return all;
}

static void compareCoeffs(const ThirdOrderPolynomialModel &pre, const ThirdOrderPolynomialModel &post,
                          const std::string &realText, Result &r)
{
	// Token per coefficient as it appears in the file that is actually read, for the record.
	std::vector<std::string> token(2 * NC);
	{
		std::istringstream in(realText);
		std::string line;
		while (std::getline(in, line))
		{
			std::istringstream ls(line);
			std::string a, b, c;
			ls >> a >> b >> c;
			char *e = nullptr;
			const long idx = std::strtol(a.c_str(), &e, 10);
			if (!a.empty() && *e == 0 && !b.empty() && c.empty() && idx >= 0 && idx < 2 * NC) token[idx] = b;
		}
	}
	for (int i = 0; i < 2 * NC; i++)
	{
		const double a = i < NC ? pre.coeffX(i) : pre.coeffY(i - NC);
		const double b = i < NC ? post.coeffX(i) : post.coeffY(i - NC);
		const bool eq = std::memcmp(&a, &b, sizeof a) == 0;
		const double abs_err = b - a;
		const double rel = a != 0 ? abs_err / a : (b != 0 ? INFINITY : 0.0);
		if (!eq) r.coeff_not_bit_equal++;
		r.max_coeff_abs_err = std::max(r.max_coeff_abs_err, std::fabs(abs_err));
		if (std::isfinite(rel)) r.max_coeff_rel_err = std::max(r.max_coeff_rel_err, std::fabs(rel));
		r.coeff_rows.push_back({r.fixture, r.route, i < NC ? "X" : "Y", std::to_string(i < NC ? i : i - NC),
		                        std::to_string(i), num(a), hexf(a), num(b), hexf(b), eq ? "1" : "0",
		                        num(abs_err), std::isfinite(rel) ? num(rel) : "inf", token[i]});
	}
}

static Result runRoute(const Spec &spec, const Fixture &fx, const std::string &route,
                       const std::string &filePath, std::ofstream *csv)
{
	Result r;
	r.fixture = fx.name; r.route = route;
	ThirdOrderPolynomialModel pre, post;
	fillModel(pre, fx.cx, fx.cy);
	post.coeffX.resize(NC); post.coeffX.initZeros();
	post.coeffY.resize(NC); post.coeffY.initZeros();
	r.read_ok = realRead(post, filePath, r.read_err);
	if (!r.read_ok) return r;
	compareCoeffs(pre, post, slurp(filePath), r);
	evaluate(spec, pre, post, csv, fx.name + ":" + route, r);
	return r;
}

static void jsonSample(std::ostream &o, const Spec &spec, const Sample &s)
{
	o << "{\"geometry\":\"" << spec.geoms[s.g].name << "\",\"frame\":" << s.frame << ",\"px\":" << num(s.px)
	  << ",\"py\":" << num(s.py) << ",\"x_norm\":" << num(s.xn) << ",\"y_norm\":" << num(s.yn)
	  << ",\"pre\":[" << num(s.pre_x) << "," << num(s.pre_y) << "],\"post\":[" << num(s.post_x) << ","
	  << num(s.post_y) << "],\"err\":[" << num(s.ex) << "," << num(s.ey) << "],\"vec\":" << num(s.vec) << "}";
}

static void jsonResult(std::ostream &o, const Spec &spec, const Result &r)
{
	o << "{\"fixture\":\"" << r.fixture << "\",\"route\":\"" << r.route << "\",\"read_ok\":"
	  << (r.read_ok ? "true" : "false");
	if (!r.read_ok) { o << ",\"read_error\":\"" << jesc(r.read_err) << "\"}"; return; }
	o << ",\"coefficients_not_bit_equal\":" << r.coeff_not_bit_equal
	  << ",\"max_coeff_abs_err\":" << num(r.max_coeff_abs_err)
	  << ",\"max_coeff_rel_err_finite\":" << num(r.max_coeff_rel_err)
	  << ",\"samples\":" << r.all.n
	  << ",\"max_abs_ex\":" << num(r.all.max_ex) << ",\"max_abs_ey\":" << num(r.all.max_ey)
	  << ",\"max_vec\":" << num(r.all.max_vec)
	  << ",\"rms_vec\":" << num(r.all.n ? std::sqrt(r.all.sum_sq / r.all.n) : 0.0) << ",\n  \"ranges\":{";
	for (size_t k = 0; k < spec.ranges.size(); k++)
	{
		const Agg &a = r.ranges[k];
		o << (k ? "," : "") << "\n    \"" << spec.ranges[k].name << "\":{\"frames\":[" << spec.ranges[k].lo << ","
		  << spec.ranges[k].hi << "],\"max_abs_ex\":" << num(a.max_ex) << ",\"max_abs_ey\":" << num(a.max_ey)
		  << ",\"max_vec\":" << num(a.max_vec) << ",\"worst_vec_at\":";
		jsonSample(o, spec, a.at_vec);
		o << "}";
	}
	o << "\n  },\n  \"worst_component_x_at\":";
	jsonSample(o, spec, r.all.at_ex);
	o << ",\n  \"worst_component_y_at\":";
	jsonSample(o, spec, r.all.at_ey);
	o << ",\n  \"top5_by_vec\":[";
	for (size_t k = 0; k < r.top.size(); k++) { o << (k ? "," : "") << "\n    "; jsonSample(o, spec, r.top[k]); }
	o << "\n  ]}";
}

static std::string csvRow(const std::vector<std::string> &v)
{
	std::string s;
	for (size_t i = 0; i < v.size(); i++) s += (i ? "," : "") + v[i];
	return s;
}

int main(int argc, char **argv)
{
	if (argc != 3) { std::cerr << "usage: roundtrip_oracle <fixtures.txt> <outdir>\n"; return 2; }
	try
	{
		const Spec spec = loadSpec(argv[1]);
		const fs::path out = argv[2];
		fs::create_directories(out / "written_star");
		fs::create_directories(out / "fullprecision_star");
		std::ofstream samples(out / "samples_full.csv");
		samples << "case,geometry,frame,px,py,x_norm,y_norm,pre_x,pre_y,post_x,post_y,err_x,err_y,err_vec\n";
		std::ofstream coeffs(out / "coefficients.csv");
		coeffs << "fixture,route,dim,coeff_in_dim,coeff_index,pre_write,pre_write_hex,post_read,post_read_hex,bit_equal,abs_err,rel_err,written_token\n";
		std::ofstream perframe(out / "per_frame_max_vec.csv");
		perframe << "fixture,route,frame,max_vec_err_px\n";
		std::ofstream json(out / "summary.json");
		json << "{\"fixtures\":[\n";

		std::vector<Result> results;
		bool first = true;
		for (const Fixture &fx : spec.fixtures)
		{
			// Route A: the real write, then the real read.
			ThirdOrderPolynomialModel pre;
			fillModel(pre, fx.cx, fx.cy);
			const std::string pathA = (out / "written_star" / (fx.name + ".star")).string();
			const std::string realText = realWrite(pre, pathA);
			Result a = runRoute(spec, fx, "real-write-read", pathA, &samples);
			// Route B (TEST-ONLY): full-precision independent file.
			const std::string pathB = (out / "fullprecision_star" / (fx.name + ".star")).string();
			{ std::ofstream f(pathB); f << fullPrecisionText(realText, fx.cx, fx.cy, -1, 0.0); }
			Result b = runRoute(spec, fx, "fullprecision-test-only", pathB, &samples);
			for (Result *r : {&a, &b})
			{
				for (auto &row : r->coeff_rows) coeffs << csvRow(row) << "\n";
				for (int f = 0; f < (int) r->per_frame_max.size() && r->read_ok; f++)
					perframe << r->fixture << "," << r->route << "," << f << "," << num(r->per_frame_max[f]) << "\n";
				json << (first ? "" : ",\n"); first = false;
				jsonResult(json, spec, *r);
				results.push_back(*r);
			}
		}
		bool any_failed = false;
		for (const Result &r : results) any_failed = any_failed || !r.read_ok;
		json << "\n],\n\"any_read_failed\":" << (any_failed ? "true" : "false") << ",\n";

		// K3 injected-error control on F02_ordinary (looked up by name).
		const Fixture *f02 = nullptr;
		for (const Fixture &fx : spec.fixtures) if (fx.name == "F02_ordinary") f02 = &fx;
		json << "\"injected_control\":";
		if (!f02) json << "null\n";
		else
		{
			const double delta = 1e-6;
			ThirdOrderPolynomialModel pre;
			fillModel(pre, f02->cx, f02->cy);
			const std::string tmp = (out / "written_star" / "_inject_scratch.star").string();
			const std::string realText = realWrite(pre, tmp);
			fs::remove(tmp);
			const std::string pathC = (out / "fullprecision_star" / "F02_ordinary_plus1e-6_Yidx17.star").string();
			{ std::ofstream f(pathC); f << fullPrecisionText(realText, f02->cx, f02->cy, NC + 17, delta); }
			Result c = runRoute(spec, *f02, "injected-Yidx17-plus-1e-6", pathC, nullptr);
			ThirdOrderPolynomialModel post;
			std::string err;
			realRead(post, pathC, err);
			const double d = post.coeffY(17) - pre.coeffY(17);
			double predicted = 0; Sample at{};
			for (size_t gi = 0; gi < spec.geoms.size(); gi++)
			{
				const Geometry &g = spec.geoms[gi];
				std::vector<std::pair<double, double> > pos;
				for (double fy : spec.fractions)
					for (double fx : spec.fractions) pos.push_back({fx * (g.w - 1), fy * (g.h - 1)});
				for (auto &p : spec.extra) pos.push_back(p);
				for (auto &p : pos)
				{
					const double xn = p.first / g.w - 0.5, yn = p.second / g.h - 0.5;
					for (int f = 0; f < spec.frames; f++)
					{
						const double v = std::fabs(d * (double) f * f * f * xn * yn);
						if (v > predicted) { predicted = v; at.g = (int) gi; at.frame = f; at.px = p.first; at.py = p.second; }
					}
				}
			}
			const double rel = predicted != 0 ? std::fabs(c.all.max_ey - predicted) / predicted : INFINITY;
			json << "{\"delta_requested\":" << num(delta) << ",\"delta_read_minus_pre\":" << num(d)
			     << ",\"predicted_max_abs_ey\":" << num(predicted) << ",\"predicted_at\":{\"geometry\":\""
			     << spec.geoms[at.g].name << "\",\"frame\":" << at.frame << ",\"px\":" << num(at.px)
			     << ",\"py\":" << num(at.py) << "},\"measured_max_abs_ex\":" << num(c.all.max_ex)
			     << ",\"measured_max_abs_ey\":" << num(c.all.max_ey) << ",\"relative_difference\":" << num(rel)
			     << ",\"measured_argmax_y_at\":";
			jsonSample(json, spec, c.all.at_ey);
			json << ",\"K3_criteria_met\":"
			     << ((c.all.max_ex == 0 && rel < 1e-9 && c.all.at_ey.frame == at.frame) ? "true" : "false") << "}\n";
		}
		json << "}\n";

		// Compact stdout table.
		std::printf("%-28s %-24s %5s %7s %13s %13s %13s | late24 max_vec\n", "fixture", "route", "readok",
		            "coefNEq", "max_coef_abs", "max_vec_px", "rms_vec_px");
		for (const Result &r : results)
		{
			if (!r.read_ok) { std::printf("%-28s %-24s READ FAILED: %s\n", r.fixture.c_str(), r.route.c_str(), r.read_err.c_str()); continue; }
			double l24 = 0;
			for (size_t k = 0; k < spec.ranges.size(); k++) if (spec.ranges[k].name == "late24") l24 = r.ranges[k].max_vec;
			std::printf("%-28s %-24s %5s %7d %13.6e %13.6e %13.6e | %.6e\n", r.fixture.c_str(), r.route.c_str(),
			            "yes", r.coeff_not_bit_equal, r.max_coeff_abs_err, r.all.max_vec,
			            r.all.n ? std::sqrt(r.all.sum_sq / r.all.n) : 0.0, l24);
		}
		return 0;
	}
	catch (RelionError &e) { std::cerr << "RelionError: " << e.msg << "\n"; return 1; }
	catch (std::exception &e) { std::cerr << "error: " << e.what() << "\n"; return 1; }
}
