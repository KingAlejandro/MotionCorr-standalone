// Device-free control for the sparse hot-pixel neighbour selection.
//
// The resident CUDA path no longer downloads the movie to pick replacement values;
// it resolves the drawn index to a coordinate and fetches that one pixel. This is
// only exact if the coordinate it resolves is the same entry the original buffer
// gather would have handed back for the same index. That equality is checked here
// against a literal transcription of the original loop, over masks that include the
// cases the real data produces: isolated defects, edges, corners, and blocks dense
// enough to drive n_ok below the Gaussian threshold.

#include "src/defect_neighbours.h"

#include <cstdio>
#include <string>
#include <vector>

using namespace mc_defect;

static int failures = 0;
static void check(bool c, const char *what) {
    if (!c) { std::printf("FAIL: %s\n", what); failures++; }
}

struct Mask {
    const std::vector<char> *m; int nx;
    bool operator()(int y, int x) const { return (*m)[(size_t)y * nx + x] != 0; }
};

// Literal transcription of the original gather in motioncorr_runner.cpp.
static void referenceGather(const std::vector<char> &bad, const std::vector<float> &img,
                            int nx, int ny, int cy, int cx, int d_max,
                            std::vector<float> &pbuf) {
    pbuf.clear();
    for (int dy = -d_max; dy <= d_max; dy++) {
        int y = cy + dy;
        if (y < 0 || y >= ny) continue;
        for (int dx = -d_max; dx <= d_max; dx++) {
            int x = cx + dx;
            if (x < 0 || x >= nx) continue;
            if (bad[(size_t)y * nx + x]) continue;
            pbuf.push_back(img[(size_t)y * nx + x]);
        }
    }
}

static void runCase(const char *name, int nx, int ny, int d_max,
                    const std::vector<char> &bad) {
    std::vector<float> img((size_t)nx * ny);
    for (size_t i = 0; i < img.size(); i++) img[i] = (float)(i * 7 % 1013) + 0.5f;
    Mask mask{&bad, nx};

    long checked = 0, ranks = 0;
    std::vector<float> pbuf;
    for (int cy = 0; cy < ny; cy++) {
        for (int cx = 0; cx < nx; cx++) {
            if (!bad[(size_t)cy * nx + cx]) continue;
            referenceGather(bad, img, nx, ny, cy, cx, d_max, pbuf);
            const int n_ok = countValidNeighbours(mask, nx, ny, cy, cx, d_max);
            if (n_ok != (int)pbuf.size()) {
                std::printf("FAIL: %s n_ok %d != reference %zu at (%d,%d)\n",
                            name, n_ok, pbuf.size(), cy, cx);
                failures++; return;
            }
            checked++;
            for (int r = 0; r < n_ok; r++) {
                int y = -1, x = -1;
                if (!nthValidNeighbour(mask, nx, ny, cy, cx, d_max, r, &y, &x)) {
                    std::printf("FAIL: %s rank %d unresolved at (%d,%d)\n", name, r, cy, cx);
                    failures++; return;
                }
                if (img[(size_t)y * nx + x] != pbuf[r]) {
                    std::printf("FAIL: %s rank %d value mismatch at (%d,%d)\n", name, r, cy, cx);
                    failures++; return;
                }
                ranks++;
            }
            // Out-of-range ranks must be refused, not silently clamped: that is what
            // would turn a dense-defect miscount into a wrong replacement value.
            int y = -99, x = -99;
            check(!nthValidNeighbour(mask, nx, ny, cy, cx, d_max, n_ok, &y, &x),
                  "rank == n_ok is refused");
            check(!nthValidNeighbour(mask, nx, ny, cy, cx, d_max, -1, &y, &x),
                  "negative rank is refused");
            check(y == -99 && x == -99, "a refused rank leaves the outputs untouched");
        }
    }
    std::printf("  %-28s defects=%ld ranks=%ld\n", name, checked, ranks);
    check(checked > 0, "case exercised at least one defect");
}

// The hot-pixel bad list used to be built by scanning the whole final mask.
// mergeBadIndices must return that same list from (pre-mask, new hits).
static void scanList(const std::vector<char> &bad, int nx, int ny,
                     std::vector<int> &xs, std::vector<int> &ys) {
    xs.clear(); ys.clear();
    for (int i = 0; i < ny; i++)
        for (int j = 0; j < nx; j++)
            if (bad[(size_t)i * nx + j]) { xs.push_back(j); ys.push_back(i); }
}

static void mergeCases() {
    const int nx = 37, ny = 29;  // odd nx so x/y decomposition errors cannot cancel
    unsigned state = 12345u;
    auto next = [&]() { state = state * 1103515245u + 12345u; return (state >> 16) & 0x7fff; };
    long compared = 0;
    for (int trial = 0; trial < 200; trial++) {
        std::vector<char> premask((size_t)nx * ny, 0), bad;
        const int pre_rate = trial % 4 == 0 ? 0 : 1 + trial % 7;   // includes empty pre-masks
        for (auto &v : premask) v = (int)(next() % 100) < pre_rate;
        bad = premask;
        std::vector<int> pre_idx, hits;
        for (int n = 0; n < nx * ny; n++) if (premask[n]) pre_idx.push_back(n);
        // Hits are generated as the runner records them: ascending, skipping
        // pixels the pre-mask already holds.
        const int hit_rate = trial % 5 == 0 ? 0 : 1 + trial % 3;
        for (int n = 0; n < nx * ny; n++)
            if ((int)(next() % 100) < hit_rate && !bad[n]) { bad[n] = 1; hits.push_back(n); }
        std::vector<int> want_x, want_y, got_x, got_y;
        scanList(bad, nx, ny, want_x, want_y);
        if (!mergeBadIndices(pre_idx, hits, nx, got_x, got_y) ||
            got_x != want_x || got_y != want_y) {
            std::printf("FAIL: merge != full scan, trial %d (pre %zu, hits %zu)\n",
                        trial, pre_idx.size(), hits.size());
            failures++;
            return;
        }
        compared += (long)want_x.size();
    }
    std::printf("  %-28s trials=200 entries=%ld\n", "merge == full-mask scan", compared);

    std::vector<int> x, y;
    check(mergeBadIndices({}, {}, nx, x, y) && x.empty(), "empty inputs give an empty list");
    check(!mergeBadIndices({3, 2}, {}, nx, x, y), "unsorted pre-mask list is refused");
    check(!mergeBadIndices({}, {9, 4}, nx, x, y), "unsorted hit list is refused");
    check(!mergeBadIndices({2, 5}, {5}, nx, x, y), "an index in both lists is refused");
    check(!mergeBadIndices({2, 2}, {}, nx, x, y), "a repeated index is refused");
    check(!mergeBadIndices({-1, 4}, {}, nx, x, y), "a negative index is refused");
    check(!mergeBadIndices({1}, {}, 0, x, y), "nx <= 0 is refused");
}

int main(int argc, char **argv) {
    // Compiled negative controls build this test against a broken merge and pass
    // only if it detects the defect.
    const bool expect_fail = argc > 1 && std::string(argv[1]) == "--expect-fail";
    const int nx = 48, ny = 40;
    std::vector<char> bad;

    // Isolated defects, including every edge and corner.
    bad.assign((size_t)nx * ny, 0);
    const int pts[][2] = {{0,0},{0,nx-1},{ny-1,0},{ny-1,nx-1},{0,20},{ny-1,20},{20,0},{20,nx-1},{15,15},{16,30}};
    for (auto &p : pts) bad[(size_t)p[0]*nx + p[1]] = 1;
    runCase("isolated + edges + corners", nx, ny, 2, bad);

    // A 5x5 block: the interior pixel has no valid neighbour at d_max=2, which is the
    // Gaussian-fallback case the replacement loop must reach.
    bad.assign((size_t)nx * ny, 0);
    for (int y = 10; y < 15; y++) for (int x = 10; x < 15; x++) bad[(size_t)y*nx + x] = 1;
    runCase("5x5 dense block", nx, ny, 2, bad);
    {
        Mask m{&bad, nx};
        check(countValidNeighbours(m, nx, ny, 12, 12, 2) == 0,
              "5x5 block centre has zero valid neighbours");
        check(countValidNeighbours(m, nx, ny, 12, 12, 2) <= 6,
              "5x5 block centre falls below NUM_MIN_OK");
    }

    // A full bad column and row, so windows are partly masked rather than empty.
    bad.assign((size_t)nx * ny, 0);
    for (int y = 0; y < ny; y++) bad[(size_t)y*nx + 24] = 1;
    for (int x = 0; x < nx; x++) bad[(size_t)7*nx + x] = 1;
    runCase("full row and column", nx, ny, 2, bad);

    // Everything bad: no rank is ever resolvable.
    bad.assign((size_t)nx * ny, 1);
    {
        Mask m{&bad, nx};
        int y = -1, x = -1;
        check(countValidNeighbours(m, nx, ny, 5, 5, 2) == 0, "fully masked yields n_ok 0");
        check(!nthValidNeighbour(m, nx, ny, 5, 5, 2, 0, &y, &x), "fully masked resolves nothing");
    }

    // EER uses d_max = 4; the mapping must hold at that radius too.
    bad.assign((size_t)nx * ny, 0);
    for (int y = 20; y < 24; y++) for (int x = 6; x < 10; x++) bad[(size_t)y*nx + x] = 1;
    bad[(size_t)3*nx + 3] = 1;
    runCase("d_max=4 (EER radius)", nx, ny, 4, bad);

    mergeCases();

    if (expect_fail) {
        if (failures) { std::printf("negative control: defect detected (%d check(s) failed)\n", failures); return 0; }
        std::printf("negative control: mutant passed every check\n");
        return 1;
    }
    if (failures) { std::printf("%d check(s) failed\n", failures); return 1; }
    std::printf("defect neighbours: all checks passed\n");
    return 0;
}
