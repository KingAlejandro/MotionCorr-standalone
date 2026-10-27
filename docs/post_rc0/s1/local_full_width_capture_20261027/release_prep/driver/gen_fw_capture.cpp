// Test generator: a real FullWidthPair capture (actual capture code, actual MotioncorrRunner::ccfWeightAt weights, 2 executed iterations) for the witness tests.
#include "src/motioncorr_runner.h"
#include "src/local_ccf_capture.h"
#include <iostream>
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    try {
        MultidimArray<float> input(32, 42); for (size_t i = 0; i < 1344; ++i) input.data[i] = float(std::sin(.13 * i) + .3 * std::cos(.037 * i));
        MultidimArray<fComplex> ft; NewFFT::FourierTransform(input, ft);
        std::vector<RFLOAT> zero(5, 0);
        MultidimArray<float> weight(32, 22);
        for (int y = 0; y < 32; ++y) { const int ly = y > 16 ? y - 32 : y; for (int x = 0; x < 22; ++x) DIRECT_A2D_ELEM(weight, y, x) = MotioncorrRunner::ccfWeightAt(ly, x, 32, (RFLOAT)42, 150); }
        LocalCcfCaptureSession session(argv[1], "witness-test-movie", 128, 96, 5, LocalCcfDiagnostic::Mode::FullWidthPair);
        const int geometry[2][6] = {{84, 126, 0, 32, 104, 15}, {42, 84, 64, 96, 62, 79}};
        for (auto& g : geometry) {
            auto c = session.patch(g[0], g[1], g[2], g[3], g[4], g[5], zero, zero);
            std::vector<MultidimArray<fComplex>> fs(5, ft); MultidimArray<fComplex> ref = ft;
            for (int i = 0; i < 5; ++i) c->clipped(i, input);
            c->configure(fs, 42, 32, 15, 1, 1, 150, weight, 42);
            for (int iter = 1; iter <= 2; ++iter) {
                c->begin(iter, fs, ref, zero, zero);
                for (int i = 0; i < 5; ++i) {
                    MultidimArray<fComplex> spectrum = ft; MultidimArray<float> map; c->preDc(i, spectrum); spectrum.data[0] = fComplex(0, 0); c->postDc(i, spectrum);
                    NewFFT::inverseFourierTransform(spectrum, map, NewFFT::FwdOnly, true, c->fftObserver(i));
                    auto& p = c->peak(i); p.posx = i; p.posy = -i; p.maxval = map.data[0]; p.verdict = (i % 3 == 0) ? 0 : 1;
                    if (p.verdict == 0) { p.coupled_dx = .125 * i; p.coupled_dy = -.0625 * i; }
                    p.separable_x = p.raw_x = p.scaled_x = .5 * i; p.separable_y = p.raw_y = p.scaled_y = -.25 * i;
                    c->result(i, spectrum, map);
                }
                c->rawResults(); c->end(fs, zero, zero, zero, zero, iter == 1 ? .9 : .1, .5);
            }
            c->finish(true, 2, zero, zero); c->reported(zero, zero, zero, zero);
        }
        session.finish();
    } catch (const std::exception& e) { std::cerr << e.what() << "\n"; return 1; }
    return 0;
}
