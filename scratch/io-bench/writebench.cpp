// Isolates the MRC output cost. Mode "cur" replicates src/rwMRC.h writeMRC:
// a full-size scratch buffer, an unconditional cast copy, a whole-file fcntl
// write lock, then one fwrite. Mode "direct" drops the buffer and the copy.
// Mode "nolock" keeps the copy but drops the fcntl. Same bytes land either way.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <string>
#include <vector>
#include <chrono>
#include <unistd.h>
#include <fcntl.h>

static double now_s() {
	using namespace std::chrono;
	return duration<double>(steady_clock::now().time_since_epoch()).count();
}

static void lockWhole(FILE *f, short type) {
	struct flock fl{};
	fl.l_type = type; fl.l_whence = SEEK_SET; fl.l_start = 0; fl.l_len = 0; fl.l_pid = getpid();
	fcntl(fileno(f), type == F_UNLCK ? F_SETLK : F_SETLKW, &fl);
}

int main(int argc, char **argv) {
	if (argc < 5) { fprintf(stderr, "usage: %s <cur|nolock|direct> <dir> <nfiles> <nx> <ny> [fsync]\n", argv[0]); return 2; }
	const std::string mode = argv[1], dir = argv[2];
	const int nfiles = atoi(argv[3]);
	const long nx = atol(argv[4]), ny = atol(argv[5]);
	const bool do_fsync = (argc > 6);
	const size_t n = (size_t)nx * ny, datasize = n * 4;

	std::vector<float> img(n);
	for (size_t i = 0; i < n; i++) img[i] = (float)(i % 4096) * 0.25f;
	char header[1024]; memset(header, 0, sizeof(header));

	double t0 = now_s();
	for (int k = 0; k < nfiles; k++) {
		char path[4096];
		snprintf(path, sizeof(path), "%s/bench_%03d.mrc", dir.c_str(), k);
		FILE *f = fopen(path, "w");
		if (!f) { perror("fopen"); return 1; }
		if (mode == "cur") lockWhole(f, F_WRLCK);
		fwrite(header, 1024, 1, f);
		if (mode == "direct") {
			fwrite(img.data(), datasize, 1, f);
		} else {
			char *fdata = (char*)malloc(datasize);
			memcpy(fdata, img.data(), datasize);   // castPage2Datatype float->float
			fwrite(fdata, datasize, 1, f);
			free(fdata);
		}
		if (mode == "cur") lockWhole(f, F_UNLCK);
		if (do_fsync) { fflush(f); fsync(fileno(f)); }
		fclose(f);
	}
	double t = now_s() - t0;
	printf("write mode=%-6s dir=%-28s files=%d  total_s=%.3f  per_file_s=%.3f  MB/s=%.1f  fsync=%d\n",
	       mode.c_str(), dir.c_str(), nfiles, t, t / nfiles,
	       (double)nfiles * datasize / 1048576.0 / t, (int)do_fsync);
	return 0;
}
