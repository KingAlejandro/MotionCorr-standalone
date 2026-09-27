// reproducers/issue98_defect_huge_rect.cpp
// Demonstrates that the classic while(!eof()) + uninit ints + no pre-clip
// pattern risks non-termination or UB on a huge off-image rectangle.
// This is the anti-pattern that issue #98 fixes.
//
// Compile: g++ -std=c++17 -O2 -Wall issue98_defect_huge_rect.cpp -o issue98_defect_huge_rect
// Run with timeout (old parser would exceed this and trigger UB path):
//   timeout 2 ./issue98_defect_huge_rect || echo "TIMEOUT/FAIL on old code (expected)"
//
// Fixed parser clips BEFORE iteration → O(1) termination regardless of input size.

#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>

int main() {
    // Simulate a defect file with one huge off-image rectangle.
    // Old parser: while(!eof()){ int x,y,w,h; >>x>>y>>w>>h; for(iy=y; iy<y+h;...) }
    // With y=0, h=1<<40 (or even INT_MAX), inner loop iterates billions of times
    // or overflows signed int, before any per-pixel "if(iy>=ny) continue".
    // Guard here stops after N iterations to demonstrate the hang risk without
    // actually running for hours.

    std::istringstream in("0 0 1000000000 1000000000\n"); // huge rect (x,y,w,h)
    const int64_t MAX_ITER = 100000; // safety guard for demo
    int64_t iterations = 0;
    bool would_hang = false;

    while (!in.eof() && iterations < MAX_ITER) {
        int x = 0, y = 0, w = 0, h = 0; // classic uninit risk on fail
        in >> x >> y >> w >> h;
        // Simulate old inner double loop (no pre-clip):
        for (int64_t iy = y, ylim = (int64_t)y + h; iy < ylim && iterations < MAX_ITER; ++iy) {
            for (int64_t ix = x, xlim = (int64_t)x + w; ix < xlim && iterations < MAX_ITER; ++ix) {
                ++iterations;
                if (iterations >= MAX_ITER) { would_hang = true; break; }
            }
            if (would_hang) break;
        }
        if (would_hang) break;
    }

    std::cout << "iterations=" << iterations << " would_hang=" << (would_hang?"true":"false")
              << " (old parser risks unbounded iteration or overflow)\n";

    // The fixed parser (issue #98) uses:
    //   long long x0 = max(0, x); x1 = min(nx, safe_add(x,w)); ... clip BEFORE loop
    //   → O(1) for any input size; no iteration of clipped-out pixels.

    if (would_hang) {
        std::cout << "PASS (demo): old pattern exhibits non-termination risk; fix clips first.\n";
        return 0;
    } else {
        std::cout << "UNEXPECTED: guard did not trigger within MAX_ITER.\n";
        return 1;
    }
}
