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
#pragma once
// Frozen main 116eb04 full-spectrum phase update. Keep arithmetic unchanged.
inline void fullPhaseReference(MultidimArray<fComplex> &frame, RFLOAT shiftx, RFLOAT shifty) {
	const int nfx = XSIZE(frame), nfy = YSIZE(frame);
	const int nfy_half = nfy / 2;
	const RFLOAT twoPI = 2 * PI;

// Reduce calls to SINCOS from nfx * nfy to nfx + nfy
#define USE_TABLE
#ifdef USE_TABLE
	std::vector<RFLOAT> sinx(nfx), cosx(nfx), siny(nfy), cosy(nfy);
	for (int y = 0; y < nfy; y++) {
		int ly = y;
		if (y > nfy_half) ly = y - nfy;

		const RFLOAT phase_y = twoPI * ly * shifty;
		#ifdef RELION_SINGLE_PRECISION
		SINCOSF(phase_y, &siny[y], &cosy[y]);
		#else
		SINCOS(phase_y, &siny[y], &cosy[y]);
		#endif
	}
	for (int x = 0; x < nfx; x++) {
		const RFLOAT phase_x = twoPI * x * shiftx;
		#ifdef RELION_SINGLE_PRECISION
		SINCOSF(phase_x, &sinx[x], &cosx[x]);
		#else
		SINCOS(phase_x, &sinx[x], &cosx[x]);
		#endif
	}
#endif

	for (int y = 0; y < nfy; y++) {
#ifndef USE_TABLE
		int ly = y;
		if (y > nfy_half) ly = y - nfy;
#endif
		for (int x = 0; x < nfx; x++) {
			RFLOAT a, b, c, d, ac, bd, ab_cd;
#ifdef USE_TABLE
			b = sinx[x] * cosy[y] + cosx[x] * siny[y];
			a = cosx[x] * cosy[y] - sinx[x] * siny[y];
#else
			RFLOAT phase_shift = twoPI * (x * shiftx + ly * shifty);
			#ifdef RELION_SINGLE_PRECISION
			SINCOSF(phase_shift, &b, &a);
			#else
			SINCOS(phase_shift, &b, &a);
			#endif
#endif
			c = DIRECT_A2D_ELEM(frame, y, x).real;
			d = DIRECT_A2D_ELEM(frame, y, x).imag;
			ac = a * c;
			bd = b * d;
			ab_cd = (a + b) * (c + d); // (ab_cd-ac-bd = ad+bc : but needs 4 multiplications)
			DIRECT_A2D_ELEM(frame, y, x) = fComplex(ac - bd, ab_cd - ac - bd);
		}
	}
}


#undef USE_TABLE
