/* MotionCorr processing receipts. Copyright (C) 2026 MotionCorr contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "src/movie_processing_identity.h"
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <locale>
#include <sstream>
#include <stdexcept>

namespace motioncorr_identity
{
namespace
{
std::runtime_error invalid(const std::string &why)
{
    return std::runtime_error("Invalid MotionCorr processing receipt: " + why);
}
std::string hex(const std::string &in)
{
    static const char digits[] = "0123456789abcdef";
    std::string out;
    out.reserve(in.size() * 2);
    for (unsigned char c : in) { out += digits[c >> 4]; out += digits[c & 15]; }
    return out;
}
int digit(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    throw invalid("payload is not canonical lowercase hex");
}
std::string unhex(const std::string &in)
{
    if (in.size() > MovieProcessingIdentity::MAX_PAYLOAD || in.size() % 2)
        throw invalid("payload length");
    std::string out;
    out.reserve(in.size() / 2);
    for (size_t i = 0; i < in.size(); i += 2)
        out += static_cast<char>((digit(in[i]) << 4) | digit(in[i + 1]));
    return out;
}
bool digest(const std::string &value)
{
    if (value == "none") return true;
    if (value.size() != 64) return false;
    for (char c : value) if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    return true;
}
std::string trim(const std::string &s)
{
    const size_t begin = s.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos) return "";
    return s.substr(begin, s.find_last_not_of(" \t\r\n") - begin + 1);
}
}

const std::vector<std::string> &MovieProcessingIdentity::requiredFields()
{
    static const std::vector<std::string> keys = {
        "angpix", "bfactor", "bin_factor", "ccf_downsample", "defect_digest",
        "dose_per_frame", "dose_weighting", "early_binning", "eer_grouping", "eer_upsampling",
        "engine", "engine_digest", "even_odd_split", "frames", "gain_digest", "gain_flip",
        "gain_rotation", "group_frames", "height", "input_bytes", "input_digest",
        "interpolate_shifts", "max_iter", "other_args_digest", "patch_x", "patch_y",
        "pre_exposure", "ps_grouping", "ps_size", "runtime", "save_noDW", "seed",
        "selected_frames", "skip_defect", "voltage", "width", "write_float16"
    };
    return keys;
}

MovieProcessingIdentity::MovieProcessingIdentity(const Fields &fields) : fields_(fields)
{
    if (fields_.size() != requiredFields().size()) throw invalid("missing or extra fields");
    for (const std::string &key : requiredFields())
    {
        const auto it = fields_.find(key);
        if (it == fields_.end() || it->second.empty() || it->second.size() > 4096 ||
            it->second.find_first_of("\r\n\0", 0, 3) != std::string::npos)
            throw invalid("missing/invalid field " + key);
        if (key.size() >= 7 && key.compare(key.size() - 7, 7, "_digest") == 0 && !digest(it->second))
            throw invalid("invalid digest " + key);
    }
    if (fields_.at("input_digest") == "none" || fields_.at("engine_digest") == "none")
        throw invalid("required content identity unavailable");
    if (serialize().size() > MAX_PAYLOAD) throw invalid("payload exceeds bound");
}

std::string MovieProcessingIdentity::serialize() const
{
    std::string decoded = "motioncorr-processing-v1\n";
    for (const auto &field : fields_) decoded += field.first + "=" + field.second + "\n";
    return hex(decoded);
}

MovieProcessingIdentity MovieProcessingIdentity::parse(const std::string &payload)
{
    const std::string decoded = unhex(payload);
    std::istringstream in(decoded);
    std::string line;
    if (!std::getline(in, line) || line != "motioncorr-processing-v1") throw invalid("unsupported schema");
    Fields fields;
    while (std::getline(in, line))
    {
        const size_t equals = line.find('=');
        if (equals == std::string::npos || equals == 0 ||
            !fields.emplace(line.substr(0, equals), line.substr(equals + 1)).second)
            throw invalid("malformed or duplicate field");
    }
    MovieProcessingIdentity result(fields);
    if (result.serialize() != payload) throw invalid("noncanonical field order or encoding");
    return result;
}

std::string MovieProcessingIdentity::mismatch(const MovieProcessingIdentity &requested) const
{
    for (const auto &field : fields_)
        if (field.second != requested.fields_.at(field.first)) return field.first;
    return "";
}

std::string MovieProcessingIdentity::real(double value)
{
    if (!std::isfinite(value)) throw invalid("nonfinite processing value");
    if (value == 0) value = 0; // -0 has the same operation semantics here.
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::hexfloat << value;
    return out.str();
}

std::string readProcessingReceipt(const std::string &path)
{
    std::ifstream in(path);
    if (!in) throw invalid("cannot read " + path);
    bool in_block = false, found = false, have_version = false, have_payload = false;
    std::string line, payload;
    // A hostile STAR line must not cause an unbounded allocation before its
    // payload bound is checked. getline's fixed buffer includes room for NUL.
    constexpr size_t line_limit = MovieProcessingIdentity::MAX_PAYLOAD + 128;
    std::array<char, line_limit + 2> buffer;
    while (in)
    {
        in.getline(buffer.data(), buffer.size());
        if (in.bad()) throw invalid("read failure in " + path);
        if (in.fail() && !in.eof())
            throw invalid("oversized line in " + path);
        if (in.gcount() == 0 && in.eof()) break;
        const size_t length = static_cast<size_t>(in.gcount()) - (in.eof() ? 0 : 1);
        line.assign(buffer.data(), length);
        if (line.size() > line_limit || line.find('\0') != std::string::npos)
            throw invalid("oversized or invalid line in " + path);
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        if (line.compare(0, 5, "data_") == 0)
        {
            in_block = line == "data_motioncorr_processing";
            if (in_block) { if (found) throw invalid("duplicate block in " + path); found = true; }
            continue;
        }
        if (!in_block) continue;
        std::istringstream row(line);
        std::string label, value, extra;
        if (!(row >> label >> value) || (row >> extra)) throw invalid("malformed block in " + path);
        if (label == "_rlnMotioncorrProcessingVersion")
        {
            if (have_version || value != "1") throw invalid("duplicate or unsupported version in " + path);
            have_version = true;
        }
        else if (label == "_rlnMotioncorrProcessingIdentity")
        {
            if (have_payload) throw invalid("duplicate payload in " + path);
            payload = value; have_payload = true;
        }
        else throw invalid("unknown field in " + path);
    }
    if (in.bad()) throw invalid("read failure in " + path);
    if (!found) return "";
    if (!have_version || !have_payload) throw invalid("incomplete receipt in " + path);
    MovieProcessingIdentity::parse(payload);
    return payload;
}
}
