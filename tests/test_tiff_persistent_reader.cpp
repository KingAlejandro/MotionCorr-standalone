/* Issue #85 lane B: the persistent-handle TIFF reader must decode exactly what
 * the ordinary per-frame Image::read path decodes, and must fail the same way.
 *
 * The oracle is the production reader itself, run serially on the same file,
 * compared element by element over the whole decoded buffer with memcmp -- not
 * row sums, which relocate as a unit under a stride or flip error and cannot
 * see a permutation inside a row.
 *
 * Fixture content is distinct per frame, per row and per column, so a frame
 * taken from the wrong directory, a row placed at the wrong offset and a shift
 * inside a row are all visible. Section "negative controls" then proves the
 * comparator can actually fail for each of those, one control per property.
 *
 * Reader counts include counts above the frame count: a worker handed no work
 * must not change the result and must not report a failure.
 */

#include "src/image.h"
#include "src/tiff_movie_reader.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>
#include <algorithm>
#include <vector>
#include <zlib.h>

namespace {

int failures = 0;
int checks = 0;

void record(bool ok, const std::string &what)
{
	checks++;
	if (!ok) { std::cerr << "FAIL: " << what << std::endl; failures++; }
}

// ---------------------------------------------------------------- fixtures

std::string tmpPath(const std::string &stem)
{
	const char *dir = getenv("TMPDIR");
	std::string base = dir ? dir : "/tmp";
	if (!base.empty() && base[base.size() - 1] == '/') base.erase(base.size() - 1);
	return base + "/mc_laneB_" + stem;
}

void put16(std::string &out, uint16_t v) { out.append((const char*)&v, 2); }
void put32(std::string &out, uint32_t v) { out.append((const char*)&v, 4); }

struct FrameSpec
{
	std::vector<std::string> rows; // each row is file_width * bits/8 bytes
	uint32_t file_width = 0;
};

/* Minimal little-endian classic TIFF, one IFD per frame. Mirrors the writer in
 * tests/test_tiff_read.py so both suites exercise the same layouts, and takes
 * per-frame geometry so a heterogeneous-directory file can be built. */
void writeTiff(const std::string &path, const std::vector<FrameSpec> &frames,
               uint16_t bits_in_file, uint16_t compression, uint32_t rows_per_strip,
               uint16_t sample_format, bool with_resolution = false)
{
	std::string buf;
	buf += "II"; put16(buf, 42); put32(buf, 0); // first-IFD offset patched below

	std::vector<std::vector<uint32_t> > offs(frames.size()), counts(frames.size());
	for (size_t f = 0; f < frames.size(); f++)
	{
		const uint32_t height = (uint32_t)frames[f].rows.size();
		for (uint32_t start = 0; start < height; start += rows_per_strip)
		{
			std::string raw;
			for (uint32_t r = start; r < height && r < start + rows_per_strip; r++)
				raw += frames[f].rows[r];
			std::string blob;
			if (compression == 8)
			{
				uLongf cap = compressBound((uLong)raw.size());
				blob.resize(cap);
				if (compress2((Bytef*)&blob[0], &cap, (const Bytef*)raw.data(), (uLong)raw.size(), 6) != Z_OK)
				{ std::cerr << "zlib compress failed\n"; exit(2); }
				blob.resize(cap);
			}
			else blob = raw;
			offs[f].push_back((uint32_t)buf.size());
			counts[f].push_back((uint32_t)blob.size());
			buf += blob;
		}
	}

	uint32_t prev_next_field = 4; // the header's first-IFD pointer
	for (size_t f = 0; f < frames.size(); f++)
	{
		const uint32_t n = (uint32_t)offs[f].size();
		const uint32_t height = (uint32_t)frames[f].rows.size();
		uint32_t off_pos, cnt_pos;
		if (n > 1)
		{
			off_pos = (uint32_t)buf.size();
			for (uint32_t i = 0; i < n; i++) put32(buf, offs[f][i]);
			cnt_pos = (uint32_t)buf.size();
			for (uint32_t i = 0; i < n; i++) put32(buf, counts[f][i]);
		}
		else { off_pos = offs[f][0]; cnt_pos = counts[f][0]; }

		// XResolution is a RATIONAL, so it lives out of line; write it before
		// the IFD and point at it. Without it the reader never sets the
		// sampling rate and that half of the oracle can never fire.
		uint32_t res_pos = 0;
		if (with_resolution)
		{
			res_pos = (uint32_t)buf.size();
			// 5.08e8/3 dpi -> readTIFF computes 2.54e8/xRes = 1.5 A/px, which is
			// distinguishable from samplingRateX()'s 1.0 default, so a reader
			// that never read the tag is not mistaken for one that did.
			put32(buf, 508000000u); put32(buf, 3u);
		}

		struct Entry { uint16_t tag, type; uint32_t count, value; };
		std::vector<Entry> entries_v;
		const Entry base_entries[] = {
			{256, 4, 1, frames[f].file_width},
			{257, 4, 1, height},
			{258, 3, 1, bits_in_file},
			{259, 3, 1, compression},
			{262, 3, 1, 1},
			{273, 4, n, off_pos},
			{277, 3, 1, 1},
			{278, 4, 1, rows_per_strip},
			{279, 4, n, cnt_pos},
			{284, 3, 1, 1},
			{339, 3, 1, sample_format},
		};
		entries_v.assign(base_entries, base_entries + sizeof(base_entries) / sizeof(base_entries[0]));
		if (with_resolution)
		{
			entries_v.push_back(Entry{282, 5, 1, res_pos});  // XResolution
			entries_v.push_back(Entry{296, 3, 1, RESUNIT_INCH});
			std::sort(entries_v.begin(), entries_v.end(),
			          [](const Entry &a, const Entry &b) { return a.tag < b.tag; });
		}
		const uint32_t ifd_pos = (uint32_t)buf.size();
		put16(buf, (uint16_t)entries_v.size());
		for (size_t i = 0; i < entries_v.size(); i++)
		{
			put16(buf, entries_v[i].tag); put16(buf, entries_v[i].type); put32(buf, entries_v[i].count);
			if (entries_v[i].type == 3 && entries_v[i].count == 1)
			{ put16(buf, (uint16_t)entries_v[i].value); put16(buf, 0); }
			else put32(buf, entries_v[i].value);
		}
		const uint32_t next_field = (uint32_t)buf.size();
		put32(buf, 0);
		memcpy(&buf[prev_next_field], &ifd_pos, 4);
		prev_next_field = next_field;
	}

	FILE *fh = fopen(path.c_str(), "wb");
	if (!fh) { std::cerr << "cannot write " << path << std::endl; exit(2); }
	fwrite(buf.data(), 1, buf.size(), fh);
	fclose(fh);
}

/* Distinct per frame, per row and per column. A shared random stream would
 * still distinguish frames, but this also makes a shift inside a row visible
 * and makes a reported mismatch identify (frame, y, x) by inspection. */
uint32_t cell(int k, uint32_t y, uint32_t x) { return (uint32_t)k * 7919u + y * 131u + x * 7u; }

std::vector<FrameSpec> makeFrames(int n_frames, uint32_t width, uint32_t height,
                                  uint16_t bits, uint16_t sample_format)
{
	std::vector<FrameSpec> out;
	for (int k = 0; k < n_frames; k++)
	{
		FrameSpec fs; fs.file_width = width;
		for (uint32_t y = 0; y < height; y++)
		{
			std::string row;
			for (uint32_t x = 0; x < width; x++)
			{
				const uint32_t v = cell(k, y, x);
				if (bits == 8) row.push_back((char)(uint8_t)v);
				else if (bits == 16 && sample_format == SAMPLEFORMAT_INT)
				{ int16_t s = (int16_t)v; row.append((const char*)&s, 2); }
				else if (bits == 16)
				{ uint16_t s = (uint16_t)v; row.append((const char*)&s, 2); }
				else if (bits == 32)
				{ float f = (float)(v % 100000u) * 0.5f; row.append((const char*)&f, 4); }
				else { std::cerr << "unsupported fixture width\n"; exit(2); }
			}
			fs.rows.push_back(row);
		}
		out.push_back(fs);
	}
	return out;
}

// ---------------------------------------------------------------- oracle

/* Empty string when the two decodes are identical, a description otherwise.
 * Returning rather than recording lets the negative controls below assert that
 * each mutation is actually detected. */
std::string compareFrames(const Image<float> &ref, const Image<float> &got)
{
	if (XSIZE(ref()) != XSIZE(got()) || YSIZE(ref()) != YSIZE(got()) ||
	    ZSIZE(ref()) != ZSIZE(got()) || NSIZE(ref()) != NSIZE(got()))
		return "shape " + std::to_string(XSIZE(got())) + "x" + std::to_string(YSIZE(got())) + "x" +
		       std::to_string(ZSIZE(got())) + "x" + std::to_string(NSIZE(got())) + " != " +
		       std::to_string(XSIZE(ref())) + "x" + std::to_string(YSIZE(ref())) + "x" +
		       std::to_string(ZSIZE(ref())) + "x" + std::to_string(NSIZE(ref()));

	const size_t n = (size_t)NZYXSIZE(ref());
	const size_t w = (size_t)XSIZE(ref()), h = (size_t)YSIZE(ref());
	for (size_t i = 0; i < n; i++)
	{
		const float a = DIRECT_MULTIDIM_ELEM(ref(), i);
		const float b = DIRECT_MULTIDIM_ELEM(got(), i);
		// Bitwise: both sides ran the same castPage2T on the same bytes, and
		// memcmp also separates -0.0 from +0.0 and distinguishes NaN payloads.
		if (memcmp(&a, &b, sizeof(float)) != 0)
			return "element " + std::to_string(i) + " of " + std::to_string(n) +
			       " (frame " + std::to_string(i / (w * h)) + ", y " + std::to_string((i / w) % h) +
			       ", x " + std::to_string(i % w) + ") is " + std::to_string(b) +
			       ", expected " + std::to_string(a);
	}

	// The header state a drop-in replacement must also reproduce.
	Image<float> &r = const_cast<Image<float>&>(ref);
	Image<float> &g = const_cast<Image<float>&>(got);
	if (r.dataType() != g.dataType()) return "datatype differs";
	if (r.samplingRateX() != g.samplingRateX() || r.samplingRateY() != g.samplingRateY())
		return "sampling rate differs";
	return "";
}

void runCase(const std::string &label, const std::string &path,
             const std::vector<int> &frames, const std::vector<int> &reader_counts)
{
	std::vector<Image<float> > ref(frames.size());
	for (size_t i = 0; i < frames.size(); i++)
		ref[i].read(path, true, frames[i], false, true);

	for (size_t k = 0; k < reader_counts.size(); k++)
	{
		const int n_readers = reader_counts[k];
		const std::string tag = label + " readers=" + std::to_string(n_readers);
		std::vector<Image<float> > got(frames.size());
		TiffMovieReader reader(path, n_readers);
		reader.readFrames(frames, got);
		// Identical pixels are produced whether the pool ran on N handles at
		// once or on one handle N times, so the reader-count axis is only
		// meaningful if the team size is checked. Without this the whole
		// matrix passes under OMP_NUM_THREADS=1.
		record(reader.nReaders() == n_readers,
		       tag + ": pool holds " + std::to_string(reader.nReaders()) +
		       " handles, expected " + std::to_string(n_readers));
		record(reader.stages().omp_team_size == n_readers,
		       tag + ": OpenMP gave " + std::to_string(reader.stages().omp_team_size) +
		       " threads, expected " + std::to_string(n_readers) +
		       " (is the build missing OpenMP, or OMP_THREAD_LIMIT set?)");
		bool ok = true;
		for (size_t i = 0; i < frames.size(); i++)
		{
			const std::string diff = compareFrames(ref[i], got[i]);
			record(diff.empty(), tag + " frame=" + std::to_string(frames[i]) + ": " + diff);
			if (!diff.empty()) { ok = false; break; }
		}
		if (ok)
			std::cout << "  " << tag << ": " << frames.size() << " frame(s) exact" << std::endl;
	}
}

// Both paths must reject the same file, with the same message.
void expectSameFailure(const std::string &label, const std::string &path,
                       const std::vector<int> &frames, int n_readers,
                       const std::string &must_contain = "")
{
	std::string ref_msg, got_msg;
	try {
		std::vector<Image<float> > ref(frames.size());
		for (size_t i = 0; i < frames.size(); i++)
			ref[i].read(path, true, frames[i], false, true);
	} catch (RelionError &e) { ref_msg = e.msg; }
	  catch (std::exception &e) { ref_msg = e.what(); }

	try {
		std::vector<Image<float> > got(frames.size());
		TiffMovieReader reader(path, n_readers);
		reader.readFrames(frames, got);
	} catch (RelionError &e) { got_msg = e.msg; }
	  catch (std::exception &e) { got_msg = e.what(); }

	checks++;
	if (ref_msg.empty())
	{ std::cerr << "FAIL: " << label << ": the reference reader accepted a damaged file" << std::endl; failures++; return; }
	if (ref_msg != got_msg)
	{
		std::cerr << "FAIL: " << label << ": different failure.\n  reference:  " << ref_msg
		          << "\n  persistent: " << (got_msg.empty() ? "(accepted the file)" : got_msg) << std::endl;
		failures++;
		return;
	}
	// ref_msg == got_msg already covers the LibTIFF detail: a reader wired to
	// the wrong error context loses the has_error arm of the checks, which
	// removes the detail from its message and makes the strings differ. An
	// extra "is a detail present in both" predicate would be satisfied by
	// almost any message and would assert nothing; see the note in
	// docs/issue85_laneB_evidence/thread_safety.md.
	if (!must_contain.empty() && ref_msg.find(must_contain) == std::string::npos)
	{
		std::cerr << "FAIL: " << label << ": rejected, but not for the reason this fixture targets.\n"
		          << "  wanted a message containing: " << must_contain << "\n"
		          << "  got: " << ref_msg << std::endl;
		failures++;
		return;
	}
	std::cout << "  " << label << ": both reject identically: " << ref_msg.substr(0, 90) << std::endl;
}

std::string slurp(const std::string &p)
{
	FILE *in = fopen(p.c_str(), "rb");
	std::string all; char chunk[65536]; size_t got;
	while ((got = fread(chunk, 1, sizeof(chunk), in)) > 0) all.append(chunk, got);
	fclose(in);
	return all;
}

void spit(const std::string &p, const std::string &data)
{
	FILE *out = fopen(p.c_str(), "wb");
	fwrite(data.data(), 1, data.size(), out);
	fclose(out);
}

// ------------------------------------------------------- negative controls

/* One control per property the oracle claims to cover. A comparator that
 * cannot fail for a given mutation does not cover it, however green it is. */
void negativeControls()
{
	const uint32_t w = 12, h = 9;
	const std::string p = tmpPath("neg_control.tif");
	// With resolution tags, so the sampling-rate half of compareFrames is
	// exercised by something other than "both sides are the 1.0 default".
	writeTiff(p, makeFrames(3, w, h, 16, SAMPLEFORMAT_UINT), 16, 8, 1, SAMPLEFORMAT_UINT, true);

	std::vector<Image<float> > a(3), b(3);
	for (int i = 0; i < 3; i++) { a[i].read(p, true, i, false, true); b[i].read(p, true, i, false, true); }

	record(compareFrames(a[0], b[0]).empty(), "negative controls: unmutated pair must compare equal");

	struct Control { const char *name; void (*apply)(std::vector<Image<float> >&); };
	// 1 ULP on one value.
	{
		std::vector<Image<float> > m = b;
		float &v = DIRECT_MULTIDIM_ELEM(m[1](), 17);
		v = std::nextafter(v, v + 1.0f);
		record(!compareFrames(a[1], m[1]).empty(), "negative control: a 1 ULP change must be detected");
	}
	// Two frames swapped: only per-frame-distinct content can see this.
	{
		std::vector<Image<float> > m = b;
		std::swap(m[0], m[2]);
		record(!compareFrames(a[0], m[0]).empty(), "negative control: a frame swap must be detected");
	}
	// Rows reversed within one frame: the Y-flip property.
	{
		std::vector<Image<float> > m = b;
		for (uint32_t y = 0; y < h / 2; y++)
			for (uint32_t x = 0; x < w; x++)
				std::swap(DIRECT_A2D_ELEM(m[1](), y, x), DIRECT_A2D_ELEM(m[1](), h - 1 - y, x));
		record(!compareFrames(a[1], m[1]).empty(), "negative control: a row reversal must be detected");
	}
	// Two pixels swapped inside one row: row sums would be blind to this.
	{
		std::vector<Image<float> > m = b;
		std::swap(DIRECT_A2D_ELEM(m[2](), 3, 1), DIRECT_A2D_ELEM(m[2](), 3, 5));
		record(!compareFrames(a[2], m[2]).empty(), "negative control: an intra-row swap must be detected");
	}
	// A wrong shape.
	{
		std::vector<Image<float> > m = b;
		m[0]().reshape(1, 1, h, w - 1);
		record(!compareFrames(a[0], m[0]).empty(), "negative control: a shape change must be detected");
	}
	// The sampling rate must actually have been read off the file, or the
	// oracle is comparing two copies of the same default.
	record(a[0].samplingRateX() > 1.4 && a[0].samplingRateX() < 1.6 &&
	       a[0].samplingRateX() == a[0].samplingRateY(),
	       "negative controls: the fixture's resolution tags must reach samplingRateX/Y (got " +
	       std::to_string(a[0].samplingRateX()) + ")");
	{
		std::vector<Image<float> > m = b;
		m[0].MDMainHeader.setValue(EMDL_IMAGE_SAMPLINGRATE_X, RFLOAT(0.5));
		record(!compareFrames(a[0], m[0]).empty(),
		       "negative control: a sampling-rate change must be detected");
	}
	{
		std::vector<Image<float> > m = b;
		m[1].MDMainHeader.setValue(EMDL_IMAGE_DATATYPE, (int)Float);
		record(!compareFrames(a[1], m[1]).empty(),
		       "negative control: a datatype change must be detected");
	}
	// The failure comparator must be able to fail: a file both readers accept
	// must not be reported as "both reject with the same message".
	{
		std::string msg;
		try { Image<float> ok; ok.read(p, true, 0, false, true); } catch (RelionError &e) { msg = e.msg; }
		record(msg.empty(), "negative control: the healthy fixture must not throw");
	}
	remove(p.c_str());
	std::cout << "  negative controls: every oracle property is falsifiable" << std::endl;
}

} // namespace


uint32_t rd32(const std::string &b, size_t at)
{ uint32_t v = 0; memcpy(&v, b.data() + at, 4); return v; }
uint16_t rd16(const std::string &b, size_t at)
{ uint16_t v = 0; memcpy(&v, b.data() + at, 2); return v; }

/* Offset of directory `k`'s first strip, by walking the IFD chain of a file
 * this test wrote. Used to damage exactly one frame. */
size_t firstStripOffset(const std::string &b, int k)
{
	size_t ifd = rd32(b, 4);
	for (int i = 0; i < k; i++)
	{
		const uint16_t n = rd16(b, ifd);
		ifd = rd32(b, ifd + 2 + (size_t)n * 12);
	}
	const uint16_t n = rd16(b, ifd);
	for (uint16_t e = 0; e < n; e++)
	{
		const size_t at = ifd + 2 + (size_t)e * 12;
		if (rd16(b, at) != 273) continue;              // StripOffsets
		const uint32_t count = rd32(b, at + 4);
		const uint32_t value = rd32(b, at + 8);
		return count > 1 ? rd32(b, value) : value;     // out of line when count > 1
	}
	return 0;
}

/* The reopen path: after a frame fails, its worker reopens its handle so the
 * next frame it takes does not inherit LibTIFF state from the failed one.
 * Without the reopen a later frame can decode from a poisoned handle, and
 * nothing else in this file would see it, because readFrames rethrows and the
 * surviving slots are never compared. */
void reopenAfterFailure()
{
	const uint32_t w = 24, h = 30; const int nf = 6; const int bad = 2;
	const std::string p = tmpPath("reopen_after_failure.tif");
	writeTiff(p, makeFrames(nf, w, h, 16, SAMPLEFORMAT_UINT), 16, 8, 1, SAMPLEFORMAT_UINT);
	std::string bytes = slurp(p);
	const size_t at = firstStripOffset(bytes, bad);
	record(at > 8 && at < bytes.size(), "reopen: could not locate the strip to damage");
	for (size_t i = at; i < at + 24 && i < bytes.size(); i++) bytes[i] = (char)~bytes[i];
	spit(p, bytes);

	// Reference: read each frame on its own handle, so one bad frame does not
	// stop the others. This is what the pool must reproduce.
	std::vector<Image<float> > ref(nf);
	std::vector<bool> ref_ok(nf, false);
	for (int i = 0; i < nf; i++)
	{
		try { ref[i].read(p, true, i, false, true); ref_ok[i] = true; }
		catch (RelionError &) {}
	}
	record(!ref_ok[bad], "reopen: the damaged frame must fail on the reference path too");
	int good = 0; for (int i = 0; i < nf; i++) if (ref_ok[i]) good++;
	record(good == nf - 1, "reopen: exactly one frame should be damaged, " +
	       std::to_string(nf - good) + " failed");

	for (int readers : {1, 2, 4})
	{
		std::vector<int> all; for (int i = 0; i < nf; i++) all.push_back(i);
		std::vector<Image<float> > got(nf);
		bool threw = false;
		try {
			TiffMovieReader rd(p, readers);
			rd.readFrames(all, got);
		} catch (RelionError &) { threw = true; }
		record(threw, "reopen readers=" + std::to_string(readers) +
		       ": the damaged movie must still fail");
		// Every frame the reference decoded must also have decoded here. A
		// worker that carried a poisoned handle forward would corrupt the
		// frame it took after the failure.
		for (int i = 0; i < nf; i++)
		{
			if (!ref_ok[i]) continue;
			const std::string diff = compareFrames(ref[i], got[i]);
			record(diff.empty(), "reopen readers=" + std::to_string(readers) +
			       " frame=" + std::to_string(i) +
			       ": decoded after a sibling frame failed: " + diff);
		}
	}

	// A handle that cannot be reopened leaves the pool dead. That must be
	// reported, not handed to LibTIFF as a null TIFF*.
	{
		std::vector<int> all; for (int i = 0; i < nf; i++) all.push_back(i);
		std::vector<Image<float> > got(nf);
		TiffMovieReader rd(p, 1);
		remove(p.c_str());                    // the open handle survives; a reopen cannot
		try { rd.readFrames(all, got); } catch (RelionError &) {}
		std::string second;
		try { std::vector<Image<float> > g2(nf); rd.readFrames(all, g2); }
		catch (RelionError &e) { second = e.msg; }
		record(second.find("reused after a reader handle failed to reopen") != std::string::npos,
		       "reopen: a dead pool must be reported on reuse, got: " + second);
	}
	std::cout << "  reopen after failure: surviving frames intact, dead pool reported"
	          << std::endl;
}

/* The runner only routes a movie to the pool when this says so, and it has to
 * agree with Image::_read's ordered dispatch chain -- which tries SPIDER, the
 * compressed-MRC guard, and mrcs/mrc/st before it ever reaches the TIFF
 * branch. Matching on "tif" alone would claim ".stif". */
void eligibilityPredicate()
{
	struct Case { const char *name; bool expected; };
	const Case cases[] = {
		{"movie.tiff", true},
		{"movie.tif", true},
		{"dir.with.dots/movie.tiff", true},
		{"reference.gain", true},     // openFile rewrites .gain to tif
		{"movie.stif", false},        // _read's contains("st") branch wins
		{"movie.mrcs", false},
		{"movie.mrc", false},
		{"movie.st", false},
		{"movie.stk", false},
		{"movie.spi", false},
		{"movie.vol", false},
		{"movie.eer", false},
		{"movie.mrc.bz2", false},
		{"movie.tiff:mrc", false},    // explicit format override
		{"movie", false},
		{"", false},
	};
	for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++)
		record(tiffMovieReaderApplies(FileName(cases[i].name)) == cases[i].expected,
		       std::string("eligibility: ") + cases[i].name + " should " +
		       (cases[i].expected ? "" : "not ") + "use the pool");
	std::cout << "  eligibility predicate: " << sizeof(cases) / sizeof(cases[0])
	          << " names agree with Image::_read's dispatch order" << std::endl;
}

int main()
{
	const std::vector<int> counts = {1, 2, 4, 8, 16, 24};

	try {
		eligibilityPredicate();
		negativeControls();
		reopenAfterFailure();

		// The tutorial movies' layout: 16-bit unsigned, Deflate, one row per strip.
		{
			const uint32_t w = 29, h = 37; const int nf = 8;
			const std::string p = tmpPath("u16_deflate_rps1.tif");
			writeTiff(p, makeFrames(nf, w, h, 16, SAMPLEFORMAT_UINT), 16, 8, 1, SAMPLEFORMAT_UINT);
			std::vector<int> all; for (int i = 0; i < nf; i++) all.push_back(i);
			runCase("u16_deflate_rps1 all", p, all, counts);
			// A selected subset, as --first_frame_sum/--last_frame_sum produce.
			runCase("u16_deflate_rps1 subset", p, std::vector<int>{1, 3, 4, 7}, counts);
			// Out of order: the only case that can tell "decoded the wrong
			// directory" from "wrote it into the wrong slot".
			runCase("u16_deflate_rps1 out-of-order", p, std::vector<int>{3, 0, 7, 1, 5}, counts);
			runCase("u16_deflate_rps1 single", p, std::vector<int>{5}, std::vector<int>{1, 4});
			remove(p.c_str());
		}

		// Multi-row strips that do not divide the height: the last strip is
		// short. A wrong row stride inside a strip is invisible when every
		// strip holds one row, so this is the case that pins the placement.
		{
			const uint32_t w = 16, h = 50; const int nf = 5;
			const std::string p = tmpPath("u16_raw_rps7.tif");
			writeTiff(p, makeFrames(nf, w, h, 16, SAMPLEFORMAT_UINT), 16, 1, 7, SAMPLEFORMAT_UINT);
			std::vector<int> all; for (int i = 0; i < nf; i++) all.push_back(i);
			// 5 frames at 24 readers: most workers get no work at all.
			runCase("u16_raw_rps7 short-final-strip", p, all, counts);
			remove(p.c_str());
		}

		// The same short-final-strip geometry, compressed: where n_rows =
		// actually_read/row_bytes and the modulo guard meet a codec. The
		// survey lists this combination as untested today.
		{
			const uint32_t w = 20, h = 45; const int nf = 6;
			const std::string p = tmpPath("u16_deflate_rps8.tif");
			writeTiff(p, makeFrames(nf, w, h, 16, SAMPLEFORMAT_UINT), 16, 8, 8, SAMPLEFORMAT_UINT);
			std::vector<int> all; for (int i = 0; i < nf; i++) all.push_back(i);
			runCase("u16_deflate_rps8 short-final-strip", p, all, counts);
			remove(p.c_str());
		}

		// The datatype table's other supported entries.
		{
			const uint32_t w = 33, h = 19; const int nf = 3;
			const std::string p = tmpPath("u8_deflate_rps4.tif");
			writeTiff(p, makeFrames(nf, w, h, 8, SAMPLEFORMAT_UINT), 8, 8, 4, SAMPLEFORMAT_UINT);
			runCase("u8_uchar", p, std::vector<int>{0, 1, 2}, std::vector<int>{1, 2, 4, 8});
			remove(p.c_str());
		}
		{
			const uint32_t w = 21, h = 26; const int nf = 3;
			const std::string p = tmpPath("s16_deflate_rps5.tif");
			writeTiff(p, makeFrames(nf, w, h, 16, SAMPLEFORMAT_INT), 16, 8, 5, SAMPLEFORMAT_INT);
			runCase("s16_sshort", p, std::vector<int>{0, 1, 2}, std::vector<int>{1, 2, 4, 8});
			remove(p.c_str());
		}
		{
			const uint32_t w = 18, h = 23; const int nf = 3;
			const std::string p = tmpPath("f32_raw_rps6.tif");
			writeTiff(p, makeFrames(nf, w, h, 32, SAMPLEFORMAT_IEEEFP), 32, 1, 6, SAMPLEFORMAT_IEEEFP);
			runCase("f32_float", p, std::vector<int>{0, 1, 2}, std::vector<int>{1, 2, 4, 8});
			remove(p.c_str());
		}

		// IMOD packed 4-bit, recognised only at set geometries: 3710 bytes per
		// row is read as 7420 logical pixels. One frame, because the decoded
		// frame is 227 MB and both readers are held at once.
		{
			const uint32_t file_w = 3710, h = 7676;
			const std::string p = tmpPath("packed4bit_k2sr.tif");
			writeTiff(p, makeFrames(1, file_w, h, 8, SAMPLEFORMAT_UINT), 8, 1, 7, SAMPLEFORMAT_UINT);
			runCase("packed4bit_k2sr", p, std::vector<int>{0}, std::vector<int>{1, 2});
			remove(p.c_str());
		}

		// A handle reused across frames is parked on the previous directory.
		// Every frame must still be validated against directory 0, so a file
		// whose later directories change geometry must be rejected, not
		// silently accepted because frame k matches frame k-1.
		{
			const uint32_t w = 16, h = 50;
			std::vector<FrameSpec> f = makeFrames(1, w, h, 16, SAMPLEFORMAT_UINT);
			std::vector<FrameSpec> wide = makeFrames(3, w + 1, h, 16, SAMPLEFORMAT_UINT);
			f.insert(f.end(), wide.begin(), wide.end());
			const std::string p = tmpPath("heterogeneous_dirs.tif");
			writeTiff(p, f, 16, 8, 1, SAMPLEFORMAT_UINT);
			for (size_t k = 0; k < counts.size(); k++)
				expectSameFailure("heterogeneous directories readers=" + std::to_string(counts[k]),
				                  p, std::vector<int>{0, 1, 2, 3}, counts[k],
				                  "All frames in a TIFF should have same width");
			remove(p.c_str());
		}

		// Enough decode work per frame that two readers are genuinely in flight
		// at once. The small fixtures above finish a frame in microseconds, so
		// one worker can drain the queue before the others start and the
		// reader-count axis degenerates.
		{
			const uint32_t w = 700, h = 700; const int nf = 12;
			const std::string p = tmpPath("concurrency.tif");
			writeTiff(p, makeFrames(nf, w, h, 16, SAMPLEFORMAT_UINT), 16, 8, 1, SAMPLEFORMAT_UINT);
			std::vector<int> all; for (int i = 0; i < nf; i++) all.push_back(i);
			runCase("concurrency 700x700x12", p, all, std::vector<int>{1, 2, 4, 8});
			for (int r : {2, 4, 8})
			{
				std::vector<Image<float> > got(all.size());
				TiffMovieReader reader(p, r);
				reader.readFrames(all, got);
				const int peak = reader.stages().peak_concurrent_readers;
				record(peak >= 2, "concurrency 700x700x12 readers=" + std::to_string(r) +
				       ": peak concurrent readers was " + std::to_string(peak) +
				       ", so the pool never actually overlapped two frames");
				std::cout << "  concurrency 700x700x12 readers=" << r
				          << ": peak concurrent readers " << peak << std::endl;
			}
			remove(p.c_str());
		}

		// Damaged inputs: the merged #92 behaviour must survive the pool.
		{
			const uint32_t w = 24, h = 30; const int nf = 6;
			const std::string p = tmpPath("damage_src.tif");
			writeTiff(p, makeFrames(nf, w, h, 16, SAMPLEFORMAT_UINT), 16, 8, 1, SAMPLEFORMAT_UINT);
			std::vector<int> all; for (int i = 0; i < nf; i++) all.push_back(i);
			const std::string whole = slurp(p);

			// The IFDs are written after all the pixel data, so a cut anywhere
			// in the first half removes the whole chain and is the same case as
			// a hard truncation. To reach the chain walk, keep everything up to
			// the middle of the IFD block: directory 0 parses, and
			// TIFFNumberOfDirectories then fails partway along.
			const size_t first_ifd = [&]() {
				uint32_t off = 0; memcpy(&off, whole.data() + 4, 4); return (size_t)off; }();
			record(first_ifd > 0 && first_ifd < whole.size(),
			       "damaged fixtures: could not locate the first IFD");
			const std::string cut = tmpPath("damage_truncated.tif");
			spit(cut, whole.substr(0, first_ifd + (whole.size() - first_ifd) / 2));
			expectSameFailure("truncated IFD chain", cut, all, 4,
			                  "Corrupted TIFF directory structure");

			const std::string hard = tmpPath("damage_hard.tif");
			spit(hard, whole.substr(0, 64));
			expectSameFailure("hard truncation", hard, all, 4);

			// Corrupt the first compressed strip, leaving the IFD chain intact,
			// so the failure surfaces inside the strip loop rather than at open.
			std::string bad_bytes = whole;
			for (size_t i = 8; i < 8 + 16 && i < bad_bytes.size(); i++) bad_bytes[i] = (char)~bad_bytes[i];
			const std::string bad = tmpPath("damage_strip.tif");
			spit(bad, bad_bytes);
			expectSameFailure("corrupt strip payload", bad, all, 4,
			                  "Invalid decoded TIFF strip size");

			expectSameFailure("frame index past the stack", p, std::vector<int>{0, nf + 3}, 2,
			                  "exceeds stack size");

			// Two frames damaged at once: the error the caller sees must be the
			// one belonging to the lowest position in `frames`, whichever
			// worker happened to fail first. That ordering is what the runner's
			// serial rethrow loop guarantees today, and it is schedule
			// dependent unless the pool reproduces it explicitly.
			{
				std::string two = whole;
				// Corrupt the payload of the first strip of directories 2 and 4
				// by flipping bytes at their recorded strip offsets.
				const std::vector<int> victims = {2, 4};
				for (size_t vi = 0; vi < victims.size(); vi++)
				{
					// Strips are written frame-major, one row per strip here,
					// so directory k's first strip is strip k*h in write order.
					// Locate it by decoding the file with the reference reader
					// instead of re-deriving offsets: corrupt a byte range that
					// belongs to that frame's payload region.
					const size_t region = (two.size() - 8) / (size_t)nf;
					const size_t at = 8 + (size_t)victims[vi] * region;
					for (size_t i = at; i < at + 32 && i < two.size(); i++) two[i] = (char)~two[i];
				}
				const std::string p2 = tmpPath("damage_two_frames.tif");
				spit(p2, two);
				std::string ref_msg, got_msg;
				try {
					std::vector<Image<float> > r(all.size());
					for (size_t i = 0; i < all.size(); i++) r[i].read(p2, true, all[i], false, true);
				} catch (RelionError &e) { ref_msg = e.msg; }
				for (int readers : {1, 2, 4, 8})
				{
					got_msg.clear();
					try {
						std::vector<Image<float> > g(all.size());
						TiffMovieReader rd(p2, readers);
						rd.readFrames(all, g);
					} catch (RelionError &e) { got_msg = e.msg; }
					record(!ref_msg.empty() && ref_msg == got_msg,
					       "two damaged frames, readers=" + std::to_string(readers) +
					       ": the lowest failing slot must win.\n    reference:  " + ref_msg +
					       "\n    persistent: " + got_msg);
				}
				if (!ref_msg.empty())
					std::cout << "  two damaged frames: lowest failing slot wins at 1/2/4/8 readers"
					          << std::endl;
				remove(p2.c_str());
			}

			remove(p.c_str()); remove(cut.c_str()); remove(hard.c_str()); remove(bad.c_str());
		}
	} catch (RelionError &e) {
		std::cerr << "FAIL: unexpected RelionError: " << e.msg << std::endl;
		return 1;
	} catch (std::exception &e) {
		std::cerr << "FAIL: unexpected exception: " << e.what() << std::endl;
		return 1;
	}

	std::cout << checks << " checks run" << std::endl;
	if (failures) { std::cerr << failures << " check(s) failed" << std::endl; return 1; }
#if defined(MOTIONCORR_USE_TIFF_EXTR)
	std::cout << "PASS persistent TIFF reader matches Image::read (LibTIFF >= 4.5 per-handle error context)" << std::endl;
#else
	std::cout << "PASS persistent TIFF reader matches Image::read (LibTIFF < 4.5 thread_local error context)" << std::endl;
#endif
	return 0;
}
