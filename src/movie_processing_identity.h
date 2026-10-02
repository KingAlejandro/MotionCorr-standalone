/* MotionCorr processing receipts. Copyright (C) 2026 MotionCorr contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef MOTIONCORR_PROCESSING_IDENTITY_H
#define MOTIONCORR_PROCESSING_IDENTITY_H

#include <map>
#include <string>
#include <vector>

namespace motioncorr_identity
{
// Fixed v1 processing fields, not a general-purpose configuration format.
// The payload is ASCII hex so STAR quoting/decimal rounding cannot change it.
class MovieProcessingIdentity
{
public:
    static constexpr int VERSION = 1;
    static constexpr size_t MAX_PAYLOAD = 32768;
    using Fields = std::map<std::string, std::string>;

    explicit MovieProcessingIdentity(const Fields &fields);
    static MovieProcessingIdentity parse(const std::string &payload);
    std::string serialize() const;
    // Empty means compatible; otherwise the first differing semantic field.
    std::string mismatch(const MovieProcessingIdentity &requested) const;
    const Fields &fields() const { return fields_; }
    static const std::vector<std::string> &requiredFields();
    static std::string real(double value);
private:
    Fields fields_;
};

// Empty means legacy/no receipt. A present but malformed receipt throws; the
// resume caller must distinguish that from a torn/incomplete legacy model.
std::string readProcessingReceipt(const std::string &path);
}
#endif
