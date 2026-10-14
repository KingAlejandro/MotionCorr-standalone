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
// Frozen polynomial interpolation from main 116eb04ad359cd5bf789b28809fc2047ea155b9b.
// Only function names and the explicit worker-count parameter differ.
#pragma once
#include "src/motioncorr_runner.h"
#include "src/micrograph_model.h"
#include <omp.h>

inline void reference_realSpaceInterpolation_ThirdOrderPolynomial_withoutsum(std::vector<Image<float> > &Ialignedframes, std::vector<Image<float> > &Iframes, ThirdOrderPolynomialModel &model, std::ostream &logfile, int n_threads) {
	const int n_frames = Iframes.size();
	const int nx = XSIZE(Iframes[0]()), ny = YSIZE(Iframes[0]());
	const Matrix1D<RFLOAT> coeffX = model.coeffX, coeffY = model.coeffY;

	for (int iframe = 0; iframe < n_frames; iframe++) {
		logfile << "." << std::flush;

		const RFLOAT z = iframe, z2 = iframe * iframe;
		const RFLOAT z3 = z * z2;
		// Common terms
		const RFLOAT x_C0 = coeffX(0)  * z + coeffX(1)  * z2 + coeffX(2)  * z3;
		const RFLOAT x_C1 = coeffX(3)  * z + coeffX(4)  * z2 + coeffX(5)  * z3;
		const RFLOAT x_C2 = coeffX(6)  * z + coeffX(7)  * z2 + coeffX(8)  * z3;
		const RFLOAT x_C3 = coeffX(9)  * z + coeffX(10) * z2 + coeffX(11) * z3;
		const RFLOAT x_C4 = coeffX(12) * z + coeffX(13) * z2 + coeffX(14) * z3;
		const RFLOAT x_C5 = coeffX(15) * z + coeffX(16) * z2 + coeffX(17) * z3;
		const RFLOAT y_C0 = coeffY(0)  * z + coeffY(1)  * z2 + coeffY(2)  * z3;
		const RFLOAT y_C1 = coeffY(3)  * z + coeffY(4)  * z2 + coeffY(5)  * z3;
		const RFLOAT y_C2 = coeffY(6)  * z + coeffY(7)  * z2 + coeffY(8)  * z3;
		const RFLOAT y_C3 = coeffY(9)  * z + coeffY(10) * z2 + coeffY(11) * z3;
		const RFLOAT y_C4 = coeffY(12) * z + coeffY(13) * z2 + coeffY(14) * z3;
		const RFLOAT y_C5 = coeffY(15) * z + coeffY(16) * z2 + coeffY(17) * z3;

		#pragma omp parallel for num_threads(n_threads)
		for (int iy = 0; iy < ny; iy++) {
			const RFLOAT y = (RFLOAT)iy / ny - 0.5;
			for (int ix = 0; ix < nx; ix++) {
				const RFLOAT x = (RFLOAT)ix / nx - 0.5;
				bool valid = true;

				RFLOAT x_fitted = x_C0 + (x_C1 + x_C2 * x) * x + (x_C3 + x_C4 * y + x_C5 * x) * y;
				RFLOAT y_fitted = y_C0 + (y_C1 + y_C2 * x) * x + (y_C3 + y_C4 * y + y_C5 * x) * y;

#ifdef VALIDATE_OPTIMISED_CODE
				RFLOAT x_fitted2, y_fitted2;
				model.getShiftAt(z, x, y, x_fitted2, y_fitted2);
				if (abs(x_fitted - x_fitted2) > 1E-4 || abs(y_fitted - y_fitted2) > 1E-4) {
					std::cout << "error at " << x << ", " << y << " : " << x_fitted << " " << x_fitted2 << " " << y_fitted << " " << y_fitted2 << std::endl;
				}
#endif
				x_fitted = ix - x_fitted; y_fitted = iy - y_fitted;

				int x0 = FLOOR(x_fitted);
				int y0 = FLOOR(y_fitted);
				const int x1 = x0 + 1;
				const int y1 = y0 + 1;

				// some conditions might seem redundant but necessary when overflow happened
				if (x0 < 0 || x1 < 0) {x0 = 0; valid = false;}
				if (y0 < 0 || y1 < 0) {y0 = 0; valid = false;}
				if (x1 >= nx || x0 >= nx - 1) {x0 = nx - 1; valid = false;}
				if (y1 >= ny || y0 >= ny - 1) {y0 = ny - 1; valid = false;}
				if (!valid) {
/*					DIRECT_A2D_ELEM(Isum(), iy, ix) += DIRECT_A2D_ELEM(Iframes[iframe](), y0, x0);
#ifdef DEBUG_OWN
					if (std::isnan(DIRECT_A2D_ELEM(Isum(), iy, ix))) {
						std::cerr << "ix = " << ix << " xfit = " << x_fitted << " iy = " << iy << " ifit = " << y_fitted << std::endl;
					}
#endif
*/					DIRECT_A2D_ELEM(Ialignedframes[iframe](), iy, ix) += DIRECT_A2D_ELEM(Iframes[iframe](), y0, x0);
#ifdef DEBUG_OWN
					if (std::isnan(DIRECT_A2D_ELEM(Ialignedframes[iframe](), iy, ix))) {
						std::cerr << "ix = " << ix << " xfit = " << x_fitted << " iy = " << iy << " ifit = " << y_fitted << std::endl;
					}
#endif
					continue;
				}

				const RFLOAT fx = x_fitted - x0;
				const RFLOAT fy = y_fitted - y0;

//				std::cout << "ix = " << ix << " xfit = " << x_fitted << " iy = " << iy << " ifit = " << y_fitted << std::endl;
				const RFLOAT d00 = DIRECT_A2D_ELEM(Iframes[iframe](), y0, x0);
				const RFLOAT d01 = DIRECT_A2D_ELEM(Iframes[iframe](), y0, x1);
				const RFLOAT d10 = DIRECT_A2D_ELEM(Iframes[iframe](), y1, x0);
				const RFLOAT d11 = DIRECT_A2D_ELEM(Iframes[iframe](), y1, x1);

				const RFLOAT dx0 = LIN_INTERP(fx, d00, d01);
				const RFLOAT dx1 = LIN_INTERP(fx, d10, d11);
				const RFLOAT val = LIN_INTERP(fy, dx0, dx1);
#ifdef DEBUG_OWN
				if (std::isnan(val)) {
					std::cerr << "ix = " << ix << " xfit = " << x_fitted << " iy = " << iy << " ifit = " << y_fitted << " d00 " << d00 << " d01 " << d01 << " d10 " << d10 << " d11 " << d11 << " dx0 " << dx0 << " dx1 " << dx1 << std::endl;
				}
#endif
				//DIRECT_A2D_ELEM(Isum(), iy, ix) += val;
				DIRECT_A2D_ELEM(Ialignedframes[iframe](), iy, ix) += val;
			}
		}
	}
}

inline void reference_realSpaceInterpolation_ThirdOrderPolynomial(Image <float> &Isum, std::vector<Image<float> > &Iframes, ThirdOrderPolynomialModel &model, std::ostream &logfile, int n_threads) {
	const int n_frames = Iframes.size();
	const int nx = XSIZE(Iframes[0]()), ny = YSIZE(Iframes[0]());
	const Matrix1D<RFLOAT> coeffX = model.coeffX, coeffY = model.coeffY;

	for (int iframe = 0; iframe < n_frames; iframe++) {
		logfile << "." << std::flush;

		const RFLOAT z = iframe, z2 = iframe * iframe;
		const RFLOAT z3 = z * z2;
		// Common terms
		const RFLOAT x_C0 = coeffX(0)  * z + coeffX(1)  * z2 + coeffX(2)  * z3;
		const RFLOAT x_C1 = coeffX(3)  * z + coeffX(4)  * z2 + coeffX(5)  * z3;
		const RFLOAT x_C2 = coeffX(6)  * z + coeffX(7)  * z2 + coeffX(8)  * z3;
		const RFLOAT x_C3 = coeffX(9)  * z + coeffX(10) * z2 + coeffX(11) * z3;
		const RFLOAT x_C4 = coeffX(12) * z + coeffX(13) * z2 + coeffX(14) * z3;
		const RFLOAT x_C5 = coeffX(15) * z + coeffX(16) * z2 + coeffX(17) * z3;
		const RFLOAT y_C0 = coeffY(0)  * z + coeffY(1)  * z2 + coeffY(2)  * z3;
		const RFLOAT y_C1 = coeffY(3)  * z + coeffY(4)  * z2 + coeffY(5)  * z3;
		const RFLOAT y_C2 = coeffY(6)  * z + coeffY(7)  * z2 + coeffY(8)  * z3;
		const RFLOAT y_C3 = coeffY(9)  * z + coeffY(10) * z2 + coeffY(11) * z3;
		const RFLOAT y_C4 = coeffY(12) * z + coeffY(13) * z2 + coeffY(14) * z3;
		const RFLOAT y_C5 = coeffY(15) * z + coeffY(16) * z2 + coeffY(17) * z3;

		#pragma omp parallel for num_threads(n_threads)
		for (int iy = 0; iy < ny; iy++) {
			const RFLOAT y = (RFLOAT)iy / ny - 0.5;
			for (int ix = 0; ix < nx; ix++) {
				const RFLOAT x = (RFLOAT)ix / nx - 0.5;
				bool valid = true;

				RFLOAT x_fitted = x_C0 + (x_C1 + x_C2 * x) * x + (x_C3 + x_C4 * y + x_C5 * x) * y;
				RFLOAT y_fitted = y_C0 + (y_C1 + y_C2 * x) * x + (y_C3 + y_C4 * y + y_C5 * x) * y;

#ifdef VALIDATE_OPTIMISED_CODE
				RFLOAT x_fitted2, y_fitted2;
				model.getShiftAt(z, x, y, x_fitted2, y_fitted2);
				if (abs(x_fitted - x_fitted2) > 1E-4 || abs(y_fitted - y_fitted2) > 1E-4) {
					std::cout << "error at " << x << ", " << y << " : " << x_fitted << " " << x_fitted2 << " " << y_fitted << " " << y_fitted2 << std::endl;
				}
#endif
				x_fitted = ix - x_fitted; y_fitted = iy - y_fitted;

				int x0 = FLOOR(x_fitted);
				int y0 = FLOOR(y_fitted);
				const int x1 = x0 + 1;
				const int y1 = y0 + 1;

				// some conditions might seem redundant but necessary when overflow happened
				if (x0 < 0 || x1 < 0) {x0 = 0; valid = false;}
				if (y0 < 0 || y1 < 0) {y0 = 0; valid = false;}
				if (x1 >= nx || x0 >= nx - 1) {x0 = nx - 1; valid = false;}
				if (y1 >= ny || y0 >= ny - 1) {y0 = ny - 1; valid = false;}
				if (!valid) {
					DIRECT_A2D_ELEM(Isum(), iy, ix) += DIRECT_A2D_ELEM(Iframes[iframe](), y0, x0);
#ifdef DEBUG_OWN
					if (std::isnan(DIRECT_A2D_ELEM(Isum(), iy, ix))) {
						std::cerr << "ix = " << ix << " xfit = " << x_fitted << " iy = " << iy << " ifit = " << y_fitted << std::endl;
					}
#endif
					continue;
				}

				const RFLOAT fx = x_fitted - x0;
				const RFLOAT fy = y_fitted - y0;

//				std::cout << "ix = " << ix << " xfit = " << x_fitted << " iy = " << iy << " ifit = " << y_fitted << std::endl;
				const RFLOAT d00 = DIRECT_A2D_ELEM(Iframes[iframe](), y0, x0);
				const RFLOAT d01 = DIRECT_A2D_ELEM(Iframes[iframe](), y0, x1);
				const RFLOAT d10 = DIRECT_A2D_ELEM(Iframes[iframe](), y1, x0);
				const RFLOAT d11 = DIRECT_A2D_ELEM(Iframes[iframe](), y1, x1);

				const RFLOAT dx0 = LIN_INTERP(fx, d00, d01);
				const RFLOAT dx1 = LIN_INTERP(fx, d10, d11);
				const RFLOAT val = LIN_INTERP(fy, dx0, dx1);
#ifdef DEBUG_OWN
				if (std::isnan(val)) {
					std::cerr << "ix = " << ix << " xfit = " << x_fitted << " iy = " << iy << " ifit = " << y_fitted << " d00 " << d00 << " d01 " << d01 << " d10 " << d10 << " d11 " << d11 << " dx0 " << dx0 << " dx1 " << dx1 << std::endl;
				}
#endif
				DIRECT_A2D_ELEM(Isum(), iy, ix) += val;
			}
		}
	}
}
