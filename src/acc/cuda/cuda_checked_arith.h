#ifndef CUDA_CHECKED_ARITH_H_
#define CUDA_CHECKED_ARITH_H_

#include <cstddef>
#include <cstdint>
#include <limits>
#include <type_traits>

#include <sys/types.h>

/**
 * Overflow-checked integer arithmetic for the nvCOMP admission and staging path.
 *
 * Sizes and offsets on that path derive from TIFF tags and movie geometry, i.e.
 * from the input file. A DeviceScratchArena or pinned-cap check that compares an
 * already-wrapped size against its capacity cannot tell that the size wrapped, so
 * the arithmetic that produces those sizes has to be checked where it is done.
 *
 * Every function returns false when the exact result is not representable in the
 * destination type and then leaves @p out untouched; on true, @p out holds exactly
 * the mathematical result. Deliberately free of CUDA, nvCOMP and LibTIFF so the
 * boundaries can be tested on any host. A single portable implementation (no
 * compiler builtins) so the code that is tested is the code that ships.
 */
namespace mc_checked {

inline bool addSize(size_t a, size_t b, size_t &out) {
    if (a > std::numeric_limits<size_t>::max() - b) return false;
    out = a + b;
    return true;
}

inline bool mulSize(size_t a, size_t b, size_t &out) {
    if (b != 0 && a > std::numeric_limits<size_t>::max() / b) return false;
    out = a * b;
    return true;
}

inline bool addU64(uint64_t a, uint64_t b, uint64_t &out) {
    if (a > std::numeric_limits<uint64_t>::max() - b) return false;
    out = a + b;
    return true;
}

/** Smallest multiple of @p alignment that is >= @p value (alignment <= 1: value). */
inline bool alignUpChecked(size_t value, size_t alignment, size_t &out) {
    if (alignment <= 1) { out = value; return true; }
    const size_t rem = value % alignment;
    if (rem == 0) { out = value; return true; }
    return addSize(value, alignment - rem, out);
}

/**
 * Value-preserving integer conversion: false if @p v does not survive the round
 * trip, including sign changes (a negative signed value into an unsigned type, or
 * an unsigned value above the signed maximum).
 */
template <class T> inline bool isNegative(T v, std::true_type) { return v < T(0); }
template <class T> inline bool isNegative(T, std::false_type) { return false; }   // no "< 0" on unsigned

template <class To, class From>
inline bool convertExact(From v, To &out) {
    static_assert(std::is_integral<To>::value && std::is_integral<From>::value,
                  "convertExact is for integer types");
    const To t = static_cast<To>(v);
    if (static_cast<From>(t) != v) return false;
    if (isNegative(v, std::is_signed<From>()) != isNegative(t, std::is_signed<To>())) return false;
    out = t;
    return true;
}

/**
 * Whether the byte range [offset, offset + n) can be addressed with an off_t, which
 * is what pread takes. The exclusive end must not wrap in 64 bits and must be an
 * off_t; the start is then representable too, being no larger than the end. A
 * wrapped sum or a negative off_t would otherwise be handed to the kernel as a
 * different, valid-looking position.
 */
inline bool fileSpanFitsOffT(uint64_t offset, uint64_t n) {
    off_t end = 0;
    uint64_t end_u = 0;
    return addU64(offset, n, end_u) && convertExact(end_u, end);
}

/** ceil(a / b) for a >= 0, b > 0, without the a + b - 1 intermediate that
 *  overflows int when a is near INT_MAX. Returns 0 for b <= 0 or a < 0. */
inline int ceilDivInt(int a, int b) {
    if (a < 0 || b <= 0) return 0;
    return (int)(((long long)a + (long long)b - 1) / (long long)b);
}

/**
 * Advance the pipeline step counter, which runs 0..n_chunks inclusive: false (and k
 * unchanged) once k has reached n_chunks. Written so that k never exceeds n_chunks;
 * a plain `k <= n_chunks; k++` increments past INT_MAX when n_chunks == INT_MAX.
 */
inline bool advancePipelineStep(int &k, int n_chunks) {
    if (k >= n_chunks) return false;
    k = k + 1;
    return true;
}

} // namespace mc_checked

#endif // CUDA_CHECKED_ARITH_H_
