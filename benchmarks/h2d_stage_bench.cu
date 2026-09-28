/* H2D staging benchmark for the TIFF ingest attribution lane (Issue #85 A).
 *
 * The decode arms in tiff_ingest_bench answer what it costs to produce a host
 * movie. This answers what it then costs to put it on the device, at the two
 * representations under discussion: the float32 stack the current path
 * uploads, and the uint16 stack PR C would upload instead.
 *
 * Reports CUDA-event device time and CPU monotonic wall separately. They are
 * different quantities and are not summed or substituted for one another.
 * Allocation of the pinned buffer is timed separately from the transfer,
 * because cudaHostAlloc of a gigabyte is not free and a pinned-vs-pageable
 * comparison that hides it is not a fair one.
 */

#include <cuda_runtime.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include <time.h>

namespace {

double wallNow()
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (double)ts.tv_sec + 1e-9 * (double)ts.tv_nsec;
}

#define CK(call)                                                                   \
	do {                                                                           \
		const cudaError_t _e = (call);                                             \
		if (_e != cudaSuccess) {                                                   \
			std::cerr << "CUDA error " << cudaGetErrorString(_e)                   \
			          << " at " << __FILE__ << ":" << __LINE__ << "\n";            \
			std::exit(1);                                                          \
		}                                                                          \
	} while (0)

// The device-side widening PR C would need: uint16 -> float, no gain applied.
// Present so the uint16 upload is priced with the conversion it implies, not
// without it.
__global__ void widen_u16_to_f32(const unsigned short *__restrict__ in,
                                 float *__restrict__ out, size_t n)
{
	const size_t i = blockIdx.x * (size_t)blockDim.x + threadIdx.x;
	if (i < n) out[i] = (float)in[i];
}

double median(std::vector<double> v)
{
	std::sort(v.begin(), v.end());
	return v.empty() ? 0.0 : v[v.size() / 2];
}

} // namespace

int main(int argc, char **argv)
{
	size_t nx = 3710, ny = 3838, nframes = 24;
	int repeats = 5, device = 0;
	std::string out_path, tag;

	for (int i = 1; i < argc; i++)
	{
		const std::string a = argv[i];
		auto next = [&]() -> std::string {
			if (i + 1 >= argc) { std::cerr << "missing value for " << a << "\n"; exit(2); }
			return argv[++i];
		};
		if      (a == "--nx")      nx = std::stoul(next());
		else if (a == "--ny")      ny = std::stoul(next());
		else if (a == "--frames")  nframes = std::stoul(next());
		else if (a == "--repeats") repeats = std::stoi(next());
		else if (a == "--device")  device = std::stoi(next());
		else if (a == "--out")     out_path = next();
		else if (a == "--tag")     tag = next();
		else { std::cerr << "unknown option: " << a << "\n"; return 2; }
	}

	CK(cudaSetDevice(device));
	cudaDeviceProp prop{};
	CK(cudaGetDeviceProperties(&prop, device));
	char uuid[64] = {0};
	{
		// Same UUID the driver reports, so the record names silicon rather
		// than an ordinal that CUDA_VISIBLE_DEVICES can reshuffle.
		char *p = uuid;
		p += sprintf(p, "GPU-");
		for (int i = 0; i < 16; i++)
		{
			p += sprintf(p, "%02x", (unsigned char)prop.uuid.bytes[i]);
			if (i == 3 || i == 5 || i == 7 || i == 9) p += sprintf(p, "-");
		}
	}

	const size_t n = nx * ny * nframes;
	const size_t bytes_f32 = n * sizeof(float);
	const size_t bytes_u16 = n * sizeof(unsigned short);

	std::ostringstream J;
	J << "{\n  \"tool\": \"h2d_stage_bench\",\n";
	J << "  \"tag\": \"" << tag << "\",\n";
	J << "  \"device_name\": \"" << prop.name << "\",\n";
	J << "  \"device_uuid\": \"" << uuid << "\",\n";
	J << "  \"device_ordinal\": " << device << ",\n";
	J << "  \"nx\": " << nx << ", \"ny\": " << ny << ", \"frames\": " << nframes << ",\n";
	J << "  \"bytes_f32\": " << bytes_f32 << ", \"bytes_u16\": " << bytes_u16 << ",\n";
	J << "  \"repeats\": " << repeats << ",\n  \"arms\": [\n";

	void *d_f32 = nullptr, *d_u16 = nullptr;
	CK(cudaMalloc(&d_f32, bytes_f32));
	CK(cudaMalloc(&d_u16, bytes_u16));

	cudaEvent_t e0, e1;
	CK(cudaEventCreate(&e0));
	CK(cudaEventCreate(&e1));

	bool first = true;
	auto emit = [&](const std::string &name, size_t bytes,
	                double wall_med, double evt_med, double alloc_med) {
		if (!first) J << ",\n";
		first = false;
		J << "    {\"arm\": \"" << name << "\", \"bytes\": " << bytes
		  << ", \"wall_median_s\": " << wall_med
		  << ", \"event_median_s\": " << evt_med
		  << ", \"wall_GBps\": " << (wall_med > 0 ? (double)bytes / wall_med / 1.0e9 : 0.0)
		  << ", \"event_GBps\": " << (evt_med > 0 ? (double)bytes / evt_med / 1.0e9 : 0.0)
		  << ", \"host_alloc_median_s\": " << alloc_med << "}";
		std::cerr << "  [" << name << "] wall=" << wall_med << "s event=" << evt_med
		          << "s (" << (evt_med > 0 ? (double)bytes / evt_med / 1.0e9 : 0.0)
		          << " GB/s)" << std::endl;
	};

	// ---- pageable H2D, both representations.
	for (int which = 0; which < 2; which++)
	{
		const size_t bytes = which ? bytes_u16 : bytes_f32;
		void *dst = which ? d_u16 : d_f32;
		std::vector<char> host(bytes);
		memset(host.data(), 1, bytes);           // first touch before timing

		std::vector<double> walls, evts;
		for (int r = 0; r < repeats; r++)
		{
			CK(cudaDeviceSynchronize());
			const double w0 = wallNow();
			CK(cudaEventRecord(e0));
			CK(cudaMemcpy(dst, host.data(), bytes, cudaMemcpyHostToDevice));
			CK(cudaEventRecord(e1));
			CK(cudaEventSynchronize(e1));
			walls.push_back(wallNow() - w0);
			float ms = 0.0f;
			CK(cudaEventElapsedTime(&ms, e0, e1));
			evts.push_back(ms / 1000.0);
		}
		emit(which ? "h2d_u16_pageable" : "h2d_f32_pageable", bytes,
		     median(walls), median(evts), 0.0);
	}

	// ---- pinned H2D, both representations. Host allocation timed separately.
	for (int which = 0; which < 2; which++)
	{
		const size_t bytes = which ? bytes_u16 : bytes_f32;
		void *dst = which ? d_u16 : d_f32;

		std::vector<double> allocs, walls, evts;
		for (int r = 0; r < repeats; r++)
		{
			void *host = nullptr;
			const double a0 = wallNow();
			CK(cudaHostAlloc(&host, bytes, cudaHostAllocDefault));
			memset(host, 1, bytes);
			allocs.push_back(wallNow() - a0);

			CK(cudaDeviceSynchronize());
			const double w0 = wallNow();
			CK(cudaEventRecord(e0));
			CK(cudaMemcpy(dst, host, bytes, cudaMemcpyHostToDevice));
			CK(cudaEventRecord(e1));
			CK(cudaEventSynchronize(e1));
			walls.push_back(wallNow() - w0);
			float ms = 0.0f;
			CK(cudaEventElapsedTime(&ms, e0, e1));
			evts.push_back(ms / 1000.0);

			CK(cudaFreeHost(host));
		}
		emit(which ? "h2d_u16_pinned" : "h2d_f32_pinned", bytes,
		     median(walls), median(evts), median(allocs));
	}

	// ---- device-side widening, so the uint16 route is priced with the
	//      conversion it makes necessary.
	{
		std::vector<double> walls, evts;
		const int block = 256;
		const size_t grid = (n + block - 1) / block;
		for (int r = 0; r < repeats; r++)
		{
			CK(cudaDeviceSynchronize());
			const double w0 = wallNow();
			CK(cudaEventRecord(e0));
			widen_u16_to_f32<<<(unsigned)grid, block>>>((const unsigned short *)d_u16,
			                                            (float *)d_f32, n);
			CK(cudaEventRecord(e1));
			CK(cudaEventSynchronize(e1));
			CK(cudaGetLastError());
			walls.push_back(wallNow() - w0);
			float ms = 0.0f;
			CK(cudaEventElapsedTime(&ms, e0, e1));
			evts.push_back(ms / 1000.0);
		}
		emit("device_widen_u16_to_f32", bytes_u16 + bytes_f32,
		     median(walls), median(evts), 0.0);
	}

	J << "\n  ]\n}\n";
	CK(cudaFree(d_f32));
	CK(cudaFree(d_u16));
	CK(cudaEventDestroy(e0));
	CK(cudaEventDestroy(e1));

	if (!out_path.empty()) { std::ofstream f(out_path); f << J.str(); }
	else std::cout << J.str();
	return 0;
}
