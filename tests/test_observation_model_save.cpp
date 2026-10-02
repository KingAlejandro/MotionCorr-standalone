/*
 * MotionCorr joint STAR publication controls.
 * Copyright (C) 2026 MotionCorr contributors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "src/jaz/single_particle/obs_model.h"
#include <algorithm>
#include <stdexcept>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <csignal>
#include <sys/resource.h>

static void require(bool ok, const std::string& text)
{
    if (!ok) throw std::runtime_error(text);
}

int main(int argc, char** argv)
{
    if (argc != 3) return 2;
    const std::string mode = argv[1];
    const std::string path = argv[2];
    try
    {
        ObservationModel model;
        MetaDataTable particles;
        model.opticsMdt.addObject();
        model.opticsMdt.setValue(EMDL_CTF_VOLTAGE, 300.0);
        particles.addObject();
        particles.setValue(EMDL_MICROGRAPH_NAME, std::string("Movies/a.mrc"));
        if (mode == "write-limit")
            for (int i = 0; i < 500; ++i)
            {
                particles.addObject();
                particles.setValue(EMDL_MICROGRAPH_NAME, std::string("Movies/long_micrograph_name_") + std::to_string(i) + ".mrc");
            }
        // Cover the optional general table without inventing numerical content.
        model.generalMdt.addObject();
        model.generalMdt.setValue(EMDL_TOMO_SUBTOMOGRAM_STACK2D, false);
        std::ostringstream expected;
        model.generalMdt.setName("general"); model.generalMdt.write(expected);
        model.opticsMdt.setName("optics"); model.opticsMdt.write(expected);
        particles.setName("micrographs"); particles.write(expected);
        if (mode == "healthy")
        {
            model.save(particles, path, "micrographs");
            std::ifstream input(path);
            const std::string actual((std::istreambuf_iterator<char>(input)), {});
            require(actual == expected.str(), "healthy STAR bytes changed");
            require(!std::filesystem::exists(path + ".tmp"), "healthy temporary STAR remains");
        }
        else
        {
            if (mode == "open") std::filesystem::create_directory(path + ".tmp");
            else if (mode == "rename") std::filesystem::create_directory(path);
            else if (mode == "limit" || mode == "write-limit")
            {
                std::ofstream previous(path); previous << "previous joint STAR\n"; previous.close();
                struct rlimit inherited;
                require(getrlimit(RLIMIT_FSIZE, &inherited) == 0, "cannot read file limit");
                const rlim_t hard = inherited.rlim_max == RLIM_INFINITY ? 8192 : std::min<rlim_t>(8192, inherited.rlim_max);
                require(hard >= 128, "inherited hard file limit too small");
                const struct rlimit limit = {128, hard};
                std::signal(SIGXFSZ, SIG_IGN);
                require(setrlimit(RLIMIT_FSIZE, &limit) == 0, "cannot set finite hard file limit");
                struct rlimit actual_limit;
                require(getrlimit(RLIMIT_FSIZE, &actual_limit) == 0 &&
                        actual_limit.rlim_cur == 128 && actual_limit.rlim_max == hard &&
                        actual_limit.rlim_max != RLIM_INFINITY, "file-limit control was not finite");
                std::cout << "LIMIT soft=" << actual_limit.rlim_cur << " hard=" << actual_limit.rlim_max << std::endl;
                require(expected.str().size() > 128, "STAR does not reach injected write limit");
            }
            else return 2;
            bool rejected = false;
            try { model.save(particles, path, "micrographs"); }
            catch (RelionError& error)
            {
                const std::string marker = mode == "open" ? "Failed to open temporary STAR file" :
                    mode == "rename" ? "Failed to rename temporary STAR file" :
                    mode == "write-limit" ? "Failed to write temporary STAR file" : "Failed to flush temporary STAR file";
                require(error.msg.find(marker) != std::string::npos, "wrong STAR failure stage: " + error.msg);
                require(error.msg.find(path) != std::string::npos, "STAR failure lost path");
                rejected = true;
            }
            require(rejected, "false success: unchecked joint STAR " + mode + " failure");
            if (mode == "limit" || mode == "write-limit")
            {
                std::ifstream input(path);
                const std::string actual((std::istreambuf_iterator<char>(input)), {});
                require(actual == "previous joint STAR\n", "failed STAR write replaced prior publication");
            }
            if (mode != "open") require(!std::filesystem::exists(path + ".tmp"), "failed temporary STAR remains");
        }
        std::cout << "PASS joint STAR " << mode << std::endl;
        return 0;
    }
    catch (RelionError& error) { std::cerr << "FAIL " << error.msg << std::endl; }
    catch (const std::exception& error) { std::cerr << "FAIL " << error.what() << std::endl; }
    return 1;
}
