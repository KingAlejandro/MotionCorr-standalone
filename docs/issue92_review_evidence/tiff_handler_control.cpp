#include "src/image.h"
#if defined(EXPECT_LEGACY_TIFF) && defined(MOTIONCORR_USE_TIFF_EXTR)
#error Legacy TIFF control selected the modern branch
#endif
#if !defined(EXPECT_LEGACY_TIFF) && !defined(MOTIONCORR_USE_TIFF_EXTR)
#error Modern TIFF control selected the legacy branch
#endif
#include <atomic>
#include <thread>
#include <fstream>

std::atomic<int> outside_errors{0}, warnings{0}, failures{0};
void prior_error(const char*, const char*, va_list) { ++outside_errors; }
void prior_warning(const char*, const char*, va_list) { ++warnings; }
int main(int argc, char** argv) {
    if (argc != 3) return 2;
#if defined(MOTIONCORR_USE_TIFF_EXTR)
    std::cout << "TIFF_HANDLER_BRANCH=modern" << std::endl;
#else
    std::cout << "TIFF_HANDLER_BRANCH=legacy" << std::endl;
#endif
    TIFFSetErrorHandler(prior_error);
    TIFFSetWarningHandler(prior_warning);
    std::thread threads[4];
    for (auto& thread : threads) thread = std::thread([&] {
        for (int i = 0; i < 20; ++i) {
            try { Image<float> good; good.read(argv[1], false, -1, false, true); }
            catch (...) { ++failures; }
            bool rejected = false;
            try { Image<float> bad; bad.read(argv[2], false, -1, false, true); }
            catch (const RelionError&) { rejected = true; }
            if (!rejected) ++failures;
        }
    });
    for (auto& thread : threads) thread.join();
    TIFFError("outside-control", "must reach previous handler");
    TIFFWarning("outside-control", "must preserve warning handler");
    std::cout << "failures=" << failures << " forwarded_errors=" << outside_errors
              << " warnings=" << warnings << std::endl;
    return failures == 0 && outside_errors == 1 && warnings == 1 ? 0 : 1;
}
