#include <stdio.h>
#include <nvcomp/deflate.h>
int main(void) {
    nvcompAlignmentRequirements_t a; 
    nvcompStatus_t s = nvcompBatchedDeflateDecompressGetRequiredAlignments(
        nvcompBatchedDeflateDecompressDefaultOpts, &a);
    printf("alignments status=%d in=%zu out=%zu temp=%zu\n", (int)s,
           (size_t)a.input, (size_t)a.output, (size_t)a.temp);
    const int nx = 3710, ny = 3838;
    int rps_list[] = {1, 2, 4, 8, 16, 64, 512, 3838};
    for (int bps = 1; bps <= 2; bps++)
      for (unsigned i = 0; i < sizeof(rps_list)/sizeof(int); i++) {
        int rps = rps_list[i];
        int strips = (ny + rps - 1) / rps;
        size_t row = (size_t)nx * bps;
        size_t chunk = (size_t)rps * row;
        for (int frames = 24; frames >= 1; frames /= 2) {
            size_t n = (size_t)frames * strips, tmp = 0;
            nvcompStatus_t st = nvcompBatchedDeflateDecompressGetTempSizeAsync(
                n, chunk, nvcompBatchedDeflateDecompressDefaultOpts, &tmp,
                (size_t)frames * ny * row);
            if (st != nvcompSuccess || frames == 24)
                printf("bps=%d rps=%-5d strips=%-5d frames=%-3d chunks=%-7zu chunk_B=%-8zu status=%d temp=%zu\n",
                       bps, rps, strips, frames, n, chunk, (int)st, tmp);
            if (st != nvcompSuccess) break;
            if (frames == 1) break;
        }
      }
    return 0;
}
