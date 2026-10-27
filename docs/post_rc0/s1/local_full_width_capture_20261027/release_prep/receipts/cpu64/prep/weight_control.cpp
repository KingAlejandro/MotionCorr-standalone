// Control for the frozen weight oracle: the actual native MotioncorrRunner::ccfWeightAt, cast to float32, for x_norm 42 and 22, written as raw little-endian float32.
#include "src/motioncorr_runner.h"
#include <cstdio>
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    for (int xn : {42, 22}) {
        std::vector<float> w;
        for (int y = 0; y < 32; ++y) { const int ly = y > 16 ? y - 32 : y; for (int x = 0; x < 22; ++x) w.push_back((float)MotioncorrRunner::ccfWeightAt(ly, x, 32, (RFLOAT)xn, 150)); }
        const std::string p = std::string(argv[1]) + "/native_weight_x" + std::to_string(xn) + ".f32";
        FILE* f = std::fopen(p.c_str(), "wbx"); if (!f) return 3; std::fwrite(w.data(), 4, w.size(), f); std::fclose(f);
    }
    return 0;
}
