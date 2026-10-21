// RelionError ownership regression (#239); GPL-2.0-or-later.
#include "src/error.h"
#include <sstream>
#include <stdexcept>
#ifdef __GNUC__
#include <execinfo.h>
#endif

static void require(bool ok) { if (!ok) throw std::runtime_error("error text/backtrace changed"); }
template<class T> static auto frames(T& p) { return p.data(); }
static void** frames(void** p) { return p; }

int main(int argc, char** argv)
{
    std::ostringstream diagnostics;
    auto* old = std::cerr.rdbuf(diagnostics.rdbuf());
    if (argc > 1 && std::string(argv[1]) == "--unprinted") {
        for (int i = 0; i < 8; ++i) {
            try { throw RelionError("unprinted", "fixture.cpp", 42); }
            catch (const RelionError&) {}
        }
    } else {
        RelionError original("fixture", "fixture.cpp", 42);
        require(diagnostics.str() == "in: fixture.cpp, line 42\nERROR: \nfixture\n");
        std::ostringstream expected;
#ifdef __GNUC__
        expected << "=== Backtrace  ===\n";
        char** symbols = backtrace_symbols(frames(original.backtrace_buffer), original.size);
        for (size_t i = 0; i < original.size; ++i) expected << symbols[i] << '\n';
        free(symbols);
        expected << "==================\n";
#endif
        expected << "ERROR: \nfixture\n";
        RelionError assigned("discarded", "fixture.cpp", 43);
        assigned = original;
        try { throw original; }
        catch (RelionError caught) { // deliberately exercise the copy constructor
            RelionError copy = caught;
            std::ostringstream a, b, c, d, e;
            a << caught; b << copy; c << original; d << assigned; e << caught;
            require(a.str() == expected.str() && b.str() == a.str() && c.str() == a.str()
                    && d.str() == a.str() && e.str() == a.str());
        }
    }
    std::cerr.rdbuf(old);
    return 0;
}
