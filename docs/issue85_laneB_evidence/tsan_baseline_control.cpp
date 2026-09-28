// Control: does the SHIPPING per-frame read loop also race on std::cerr when
// several frames of a damaged movie fail at once? Same shape as
// motioncorr_runner.cpp's read loop, no persistent reader involved.
#include "src/image.h"
#include <exception>
#include <iostream>
#include <vector>
#include <omp.h>

int main(int argc, char **argv)
{
	const FileName path = argv[1];
	const int n = 6;
	std::vector<Image<float> > f(n);
	std::vector<std::exception_ptr> errs(n);
	#pragma omp parallel for num_threads(4)
	for (int i = 0; i < n; i++) {
		try { f[i].read(path, true, i, false, true); }
		catch (...) { errs[i] = std::current_exception(); }
	}
	int failed = 0;
	for (int i = 0; i < n; i++) if (errs[i]) failed++;
	std::cout << "baseline control: " << failed << "/" << n << " frames failed" << std::endl;
	return 0;
}
