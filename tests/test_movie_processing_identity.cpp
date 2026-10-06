/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "src/movie_processing_identity.h"
#include <cstdio>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <unistd.h>

using motioncorr_identity::MovieProcessingIdentity;
namespace
{
int checks = 0;
void require(bool ok, const char *why) { ++checks; if (!ok) throw std::runtime_error(why); }
void rejects(const std::function<void()> &action, const char *why)
{
    bool refused = false;
    try { action(); } catch (const std::runtime_error &) { refused = true; }
    require(refused, why);
}
std::string encoded(const std::string &text)
{
    const char *digits = "0123456789abcdef";
    std::string out;
    for (unsigned char c : text) { out += digits[c >> 4]; out += digits[c & 15]; }
    return out;
}
}
int main()
{
    const std::string path = "/tmp/motioncorr-receipt-" + std::to_string(getpid()) + ".star";
    try
    {
        MovieProcessingIdentity::Fields fields;
        for (const auto &key : MovieProcessingIdentity::requiredFields()) fields[key] = "1";
        for (const char *key : {"input_digest", "engine_digest", "gain_digest", "defect_digest", "other_args_digest"})
            fields[key] = std::string(64, 'a');
        const MovieProcessingIdentity good(fields);
        require(good.mismatch(MovieProcessingIdentity::parse(good.serialize())).empty(), "roundtrip changed identity");
        auto changed = fields; changed["bin_factor"] = "0x1p+1";
        require(good.mismatch(MovieProcessingIdentity(changed)) == "bin_factor", "missing named mismatch");
        changed = fields; changed.erase("seed");
        rejects([&]{ MovieProcessingIdentity bad(changed); }, "missing key accepted");
        changed = fields; changed["future_option"] = "1";
        rejects([&]{ MovieProcessingIdentity bad(changed); }, "extra key accepted");
        changed = fields; changed["input_digest"] = "none";
        rejects([&]{ MovieProcessingIdentity bad(changed); }, "missing input digest accepted");
        changed = fields; changed["gain_digest"] = std::string(64, 'z');
        rejects([&]{ MovieProcessingIdentity bad(changed); }, "invalid digest accepted");
        changed = fields; changed["runtime"] = std::string(4097, 'a');
        rejects([&]{ MovieProcessingIdentity bad(changed); }, "oversized field accepted");
        rejects([&]{ MovieProcessingIdentity::parse(good.serialize() + "0"); }, "odd hex accepted");
        rejects([&]{ MovieProcessingIdentity::parse(std::string(MovieProcessingIdentity::MAX_PAYLOAD + 2, '0')); }, "oversized payload accepted");
        std::string raw = "motioncorr-processing-v2\n";
        for (const auto &field : fields) raw += field.first + "=" + field.second + "\n";
        rejects([&]{ MovieProcessingIdentity::parse(encoded(raw + "seed=1\n")); }, "duplicate key accepted");
        rejects([&]{ MovieProcessingIdentity::parse(encoded("motioncorr-processing-v3\n" + raw)); }, "unsupported schema accepted");
        require(MovieProcessingIdentity::real(1.0123456789) != MovieProcessingIdentity::real(1.0123456790), "scalar rounded to STAR precision");
        require(MovieProcessingIdentity::real(-0.0) == MovieProcessingIdentity::real(0.0), "zero normalization");
        rejects([&]{ MovieProcessingIdentity::real(std::numeric_limits<double>::quiet_NaN()); }, "nonfinite scalar accepted");
        auto write = [&](const std::string &body) { std::ofstream out(path); out << body; out.close(); require(bool(out), "fixture write failed"); };
        const std::string block = "data_motioncorr_processing\n_rlnMotioncorrProcessingVersion 2\n_rlnMotioncorrProcessingIdentity " + good.serialize() + "\n";
        write("data_general\n_rlnImageSizeX 96\n" + block);
        require(motioncorr_identity::readProcessingReceipt(path) == good.serialize(), "STAR receipt roundtrip");
        write("data_general\n_rlnImageSizeX 96\n");
        require(motioncorr_identity::readProcessingReceipt(path).empty(), "legacy file not recognized");
        write(block + block);
        rejects([&]{ motioncorr_identity::readProcessingReceipt(path); }, "duplicate block accepted");
        write(block + "_rlnMotioncorrProcessingVersion 2\n");
        rejects([&]{ motioncorr_identity::readProcessingReceipt(path); }, "duplicate version accepted");
        write("data_motioncorr_processing\n_rlnMotioncorrProcessingVersion 2\n");
        rejects([&]{ motioncorr_identity::readProcessingReceipt(path); }, "torn receipt accepted");
        write(block + "_rlnUnknownSetting 1\n");
        rejects([&]{ motioncorr_identity::readProcessingReceipt(path); }, "unknown receipt field accepted");
        write(block + std::string(MovieProcessingIdentity::MAX_PAYLOAD + 129, 'a') + "\n");
        rejects([&]{ motioncorr_identity::readProcessingReceipt(path); }, "oversized STAR line accepted");
        write(block + std::string("# hidden\0value\n", 15));
        rejects([&]{ motioncorr_identity::readProcessingReceipt(path); }, "NUL STAR line accepted");
        std::remove(path.c_str());
        std::cout << "PASS MovieProcessingIdentity " << checks << " checks\n";
        return 0;
    }
    catch (const std::exception &error)
    {
        std::remove(path.c_str());
        std::cerr << error.what() << '\n'; return 1;
    }
}
