#include "src/motioncorr_runner.h"
#include "src/jaz/single_particle/new_ft.h"
#include "src/fftw.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>

void require(bool condition, const std::string &message)
{
    if (!condition) throw std::runtime_error(message);
}

int main(int argc, char **argv)
{
    try {
        require(argc == 4 || argc == 5,
                "Usage: runner_numerics bin|model|write_model|read|legacy_mtf|read_tiff input output\n"
                "       runner_numerics read_tiff_raw input output [max_rows]");
        if (std::string(argv[1]) == "read_tiff_raw") {
            // Dump decoded samples in index order. The row sums below cannot
            // see sample order within a row: swapping the two nibbles of a
            // packed 4-bit byte, for instance, leaves every row sum identical.
            // An optional row bound keeps the dump proportionate to what the
            // caller compares, since one super-resolution frame is 217 MiB.
            Image<float> movie;
            movie.read(argv[2], true, -1, false, true); // all frames, 2D stack
            const long nx = XSIZE(movie()), ny = YSIZE(movie()), nn = NSIZE(movie());
            const long all_rows = ny * nn;
            const long rows = (argc == 5) ? std::min(all_rows, static_cast<long>(textToInteger(argv[4]))) : all_rows;
            require(rows >= 0, "max_rows must not be negative");
            std::ofstream out(argv[3], std::ios::binary);
            require(out.good(), "Cannot open raw sample output");
            const long dims[3] = {nx, ny, nn};
            out.write(reinterpret_cast<const char*>(dims), sizeof(dims));
            out.write(reinterpret_cast<const char*>(MULTIDIM_ARRAY(movie())),
                      static_cast<std::streamsize>(sizeof(float)) * nx * rows);
            out.close(); // flush before judging success: ~ofstream would swallow it
            require(out.good(), "Failed writing raw samples");
            return 0;
        }
        if (std::string(argv[1]) == "read_tiff") {
            // Dump per-row sums of a decoded TIFF stack. Row sums are exact in
            // double for integer sample values, and any row-striding or Y-flip
            // error relocates whole rows, so this detects those exactly while
            // staying small enough for the large packed-4-bit geometries.
            Image<float> movie;
            movie.read(argv[2], true, -1, false, true); // all frames, 2D stack
            const long nx = XSIZE(movie()), ny = YSIZE(movie()), nn = NSIZE(movie());
            std::ofstream out(argv[3], std::ios::binary);
            require(out.good(), "Cannot open row-sum output");
            const long dims[3] = {nx, ny, nn};
            out.write(reinterpret_cast<const char*>(dims), sizeof(dims));
            for (long n = 0; n < nn; n++) {
                for (long y = 0; y < ny; y++) {
                    double rowsum = 0.0;
                    for (long x = 0; x < nx; x++)
                        rowsum += DIRECT_NZYX_ELEM(movie(), n, 0, y, x);
                    out.write(reinterpret_cast<const char*>(&rowsum), sizeof(double));
                }
            }
            require(out.good(), "Failed writing row sums");
            return 0;
        }
        if (std::string(argv[1]) == "read") {
            Micrograph parsed(argv[2]);
            return 0;
        }
        if (std::string(argv[1]) == "legacy_mtf") {
            MetaDataTable table;
            table.read(argv[2]);
            int group;
            std::string filename;
            require(table.numberOfObjects() == 1 && table.getValue(EMDL_IMAGE_OPTICS_GROUP, group) && group == 1 &&
                    table.getValue(EMDL_IMAGE_MTF_FILENAME, filename) && filename.empty(),
                    "Legacy empty trailing MTF filename was not preserved");
            return 0;
        }
        MotioncorrRunner runner;
        runner.n_threads = 1;
        if (std::string(argv[1]) == "bin") {
            Image<float> expected, actual;
            expected.read(argv[2]);
            actual.read(argv[3]);
            const int nx = XSIZE(expected()), ny = YSIZE(expected());
            MultidimArray<fComplex> full(ny, nx / 2 + 1), binned(ny / 2, nx / 4 + 1);
            NewFFT::FourierTransform(expected(), full);
            cropInFourierSpace(full, binned);
            expected().reshape(ny / 2, nx / 2);
            NewFFT::inverseFourierTransform(binned, expected());
            require(expected().sameShape(actual()), "Late-binned image has the wrong dimensions");
            float maximum = 0;
            FOR_ALL_DIRECT_ELEMENTS_IN_MULTIDIMARRAY(expected()) {
                require(std::isfinite(DIRECT_MULTIDIM_ELEM(actual(), n)), "Nonfinite binned output");
                maximum = std::max(maximum, std::abs(DIRECT_MULTIDIM_ELEM(expected(), n) - DIRECT_MULTIDIM_ELEM(actual(), n)));
            }
            require(maximum == 0, "Late-bin output differs from binning the completed full-size sum: " + std::to_string(maximum));
            std::cout << "PASS exact late-bin sum\n";
        } else {
            runner.fn_out = argv[3];
            runner.angpix = 1;
            runner.voltage = 300;
            runner.dose_per_frame = 1;
            runner.fn_defect = "";
            runner.bin_factor = 2;
            runner.do_own = true;
            Micrograph movie(argv[2], "", 2);
            movie.first_frame = 2;
            auto *poly = new ThirdOrderPolynomialModel;
            poly->coeffX.resize(18);
            poly->coeffY.resize(18);
            for (int i = 0; i < 18; ++i) {
                poly->coeffX(i) = (i + 1) / 16.0;
                poly->coeffY(i) = -(i + 1) / 32.0;
            }
            movie.model = poly;
            for (int frame = 1; frame <= movie.getNframes(); ++frame) movie.setGlobalShift(frame, 1.5, -2.5);
            const FileName output = runner.getOutputFileNames(argv[2]).withoutExtension() + ".star";
            if (std::string(argv[1]) == "write_model") {
                runner.early_binning = false;
                runner.saveModel(movie);
                return 0;
            }
            for (bool early : {false, true}) {
                runner.early_binning = early;
                for (int repeat = 0; repeat < 2; ++repeat) {
                    runner.saveModel(movie);
                    Micrograph restored(output);
                    for (int frame = 2; frame <= 5; ++frame) {
                        RFLOAT localX, localY, x, y;
                        poly->getShiftAt(frame - movie.first_frame, .25, -.25, localX, localY);
                        restored.getShiftAt(frame, .25, -.25, x, y);
                        const RFLOAT scale = early ? 2 : 1;
                        require(x == localX * scale + 1.5 && y == localY * scale - 2.5,
                                "Exported local shifts are not in original-pixel units");
                    }
                    require(poly->coeffX(0) == 1.0 / 16 && poly->coeffY(17) == -18.0 / 32,
                            "Saving mutated the runtime model");
                }
            }
            std::cout << "PASS serialized units and unchanged runtime model\n";
        }
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    } catch (RelionError &error) {
        std::cerr << error;
        return 1;
    }
}
