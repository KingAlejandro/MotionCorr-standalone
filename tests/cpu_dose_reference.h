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
// Frozen main 116eb04 doseWeighting arithmetic, kept as the exact-output control.
// Only the name and explicit thread-count argument differ from the original.
inline void referenceDoseWeighting(std::vector<MultidimArray<fComplex> > &Fframes, std::vector<RFLOAT> doses, RFLOAT apix, int n_threads) {
	const int nfx = XSIZE(Fframes[0]), nfy = YSIZE(Fframes[0]);
	const int nfy_half = nfy / 2;
	const RFLOAT nfy2 = (RFLOAT)nfy * nfy;
	const RFLOAT nfx2 = (RFLOAT)(nfx - 1) * (nfx - 1) * 4; // assuming nx is even
	const int n_frames= Fframes.size();
	const RFLOAT A = 0.245, B = -1.665, C = 2.81;

	#pragma omp parallel for num_threads(n_threads)
	for (int y = 0; y < nfy; y++) {
		int ly = y;
		if (y > nfy_half) ly = y - nfy;

		const RFLOAT ly2 = (RFLOAT)ly * ly / nfy2;
		for (int x = 0; x < nfx; x++) {
			const RFLOAT dinv2 = ly2 + (RFLOAT)x * x / nfx2;
			const RFLOAT dinv = std::sqrt(dinv2) / apix; // d = N * apix / dist, thus dinv = dist / N / angpix
			const RFLOAT Ne = (A * std::pow(dinv, B) + C) * 2; // Eq. 3. 2 comes from Eq. 5
			RFLOAT sum_weight_sq = 0;

			for (int iframe = 0; iframe < n_frames; iframe++) {
				const RFLOAT weight = std::exp(- doses[iframe] / Ne); // Eq. 5. 0.5 is factored out to Ne.
				if (std::isnan(weight)) {
					std::cerr << "dose = " <<  doses[iframe] << " Ne = " << Ne << " frm = " << iframe << " lx = " << x << " ly = " << ly << " reso = " << 1 / dinv << " weight = " << weight << std::endl;
				}
				sum_weight_sq += weight * weight;
				DIRECT_A2D_ELEM(Fframes[iframe], y, x) *= weight;
			}

			sum_weight_sq = std::sqrt(sum_weight_sq);
			if (std::isnan(sum_weight_sq)) {
				std::cerr << " Ne = " << Ne << " lx = " << x << " ly = " << ly << " reso = " << 1 / dinv << " sum_weight_sq NaN" << std::endl;
				REPORT_ERROR("Shouldn't happen.");
			}
			for (int iframe = 0; iframe < n_frames; iframe++) {
				DIRECT_A2D_ELEM(Fframes[iframe], y, x) /= sum_weight_sq; // Eq. 9
			}
		}
	}
}

