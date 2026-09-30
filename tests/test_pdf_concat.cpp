/* Concatenating a single PDF is served by a copy instead of a Ghostscript
 * re-encode. Two properties of that shortcut are asserted here:
 *
 *   1. the copy is byte-identical and reports success -- a shortcut that
 *      produced a shorter file would still produce a readable PDF, which
 *      nothing downstream would notice;
 *   2. an input that is not a PDF is NOT copied. Ghostscript rejects such a
 *      file and concatenatePDFfiles returns false; the shortcut must not turn
 *      that into a silent success. The input has to be non-empty to test
 *      this: an empty one is refused by the copy's own write check even with
 *      the signature test removed, so it cannot see that test. (An empty
 *      input is also not a failure case at all -- Ghostscript accepts it and
 *      emits a valid zero-page PDF, exit 0. An earlier version of this file
 *      asserted the opposite and failed on the first host that had gs
 *      installed.)
 *
 * Property 2's assertion is that the copy branch was not taken, which holds
 * whether or not Ghostscript is installed: with gs present it rejects a text
 * file with exit 1, without gs system() fails. Either way the answer is
 * false, and only the copy branch could return true.
 */
#include "src/CPlot2D.h"

#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

namespace {

std::string slurp(const std::string &path)
{
	std::ifstream in(path.c_str(), std::ios::binary);
	return std::string((std::istreambuf_iterator<char>(in)),
	                   std::istreambuf_iterator<char>());
}

// Minimal but structurally real, so the %PDF test and the byte count both
// operate on something a reader would accept.
const char *const ONE_PAGE_PDF =
	"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
	"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
	"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
	"trailer<</Root 1 0 R>>\n%%EOF\n";

}

int main()
{
	const std::string dir = "test_pdf_concat_tmp";
	::remove((dir + "/in.pdf").c_str());
	if (system(("mkdir -p " + dir).c_str()) != 0)
	{
		std::cerr << "cannot create " << dir << '\n';
		return 2;
	}

	int failures = 0;
	const std::string source = ONE_PAGE_PDF;
	{
		std::ofstream out((dir + "/in.pdf").c_str(), std::ios::binary);
		out << source;
	}

	::remove((dir + "/copied.pdf").c_str());
	std::vector<FileName> single;
	single.push_back(FileName(dir + "/in.pdf"));
	const bool copied = concatenatePDFfiles(FileName(dir + "/copied.pdf"), single);
	const std::string result = slurp(dir + "/copied.pdf");
	if (!copied)
	{
		std::cout << "FAIL: a one-input concatenation reported failure\n";
		failures++;
	}
	if (result != source)
	{
		std::cout << "FAIL: the copy is not byte-identical (" << result.size()
		          << " vs " << source.size() << " B)\n";
		failures++;
	}
	if (copied && result == source)
		std::cout << "PASS one-input concatenation copied " << result.size()
		          << " B exactly\n";

	// The case that exercises the signature test: non-empty, so the copy would
	// succeed and report success if the shortcut took it.
	{
		std::ofstream out((dir + "/notapdf.pdf").c_str(), std::ios::binary);
		out << "This is not a PDF, but it is long enough to be copied.\n";
	}
	::remove((dir + "/from_notapdf.pdf").c_str());
	std::vector<FileName> notapdf;
	notapdf.push_back(FileName(dir + "/notapdf.pdf"));
	if (concatenatePDFfiles(FileName(dir + "/from_notapdf.pdf"), notapdf))
	{
		std::cout << "FAIL: a non-empty non-PDF was copied and reported as a "
		             "successful concatenation\n";
		failures++;
	}
	else
	{
		std::cout << "PASS non-PDF input was not copied\n";
	}

	if (system(("rm -rf " + dir).c_str()) != 0)
		std::cerr << "warning: could not remove " << dir << '\n';
	return failures ? 1 : 0;
}
