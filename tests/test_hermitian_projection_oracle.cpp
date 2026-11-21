// SPDX-License-Identifier: GPL-2.0-or-later
#include "hermitian_projection_oracle.h"

// Only the host buffer's float components matter to the shared checker.
struct HostComplex { float x, y; };

int main() {
    try {
        hermitian_oracle::signed_zero_self_test<HostComplex>();
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
