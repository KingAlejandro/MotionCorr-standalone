/* LD_PRELOAD codec witness for issue #85.
 *
 * Counts which DEFLATE entry points LibTIFF actually calls while decoding.
 * Interposes both the zlib stream API and the libdeflate whole-buffer API, so
 * a run tells us which backend serviced each strip rather than which library
 * happens to be linked. Counts are printed to the file named by
 * MC_CODEC_WITNESS_OUT (or stderr) when the process exits.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>

static atomic_ullong n_inflate, n_inflateInit, n_ld_zlib, n_ld_deflate, n_ld_alloc, n_ld_zlib_ex;
static atomic_ullong b_inflate_out, b_ld_out;

#define NEXT(sym) ({ static void *p_##sym; if (!p_##sym) p_##sym = dlsym(RTLD_NEXT, #sym); p_##sym; })

/* --- zlib --- */
typedef struct { unsigned char *next_in; unsigned avail_in; unsigned long total_in;
                 unsigned char *next_out; unsigned avail_out; unsigned long total_out;
                 char *msg; void *state; void *zalloc, *zfree, *opaque;
                 int data_type; unsigned long adler, reserved; } mc_z_stream;

int inflate(mc_z_stream *strm, int flush)
{
	int (*real)(mc_z_stream *, int) = NEXT(inflate);
	unsigned before = strm ? strm->avail_out : 0;
	int rc = real(strm, flush);
	atomic_fetch_add(&n_inflate, 1);
	if (strm && before >= strm->avail_out)
		atomic_fetch_add(&b_inflate_out, (unsigned long long)(before - strm->avail_out));
	return rc;
}

int inflateInit_(mc_z_stream *strm, const char *version, int stream_size)
{
	int (*real)(mc_z_stream *, const char *, int) = NEXT(inflateInit_);
	atomic_fetch_add(&n_inflateInit, 1);
	return real(strm, version, stream_size);
}

/* --- libdeflate (opaque handles; we only count and forward) --- */
void *libdeflate_alloc_decompressor(void)
{
	void *(*real)(void) = NEXT(libdeflate_alloc_decompressor);
	atomic_fetch_add(&n_ld_alloc, 1);
	return real();
}

int libdeflate_zlib_decompress(void *d, const void *in, size_t in_n,
                               void *out, size_t out_n, size_t *actual_out)
{
	int (*real)(void *, const void *, size_t, void *, size_t, size_t *) =
		NEXT(libdeflate_zlib_decompress);
	int rc = real(d, in, in_n, out, out_n, actual_out);
	atomic_fetch_add(&n_ld_zlib, 1);
	if (rc == 0)
		atomic_fetch_add(&b_ld_out, (unsigned long long)(actual_out ? *actual_out : out_n));
	return rc;
}

int libdeflate_zlib_decompress_ex(void *d, const void *in, size_t in_n,
                                  void *out, size_t out_n,
                                  size_t *actual_in, size_t *actual_out)
{
	int (*real)(void *, const void *, size_t, void *, size_t, size_t *, size_t *) =
		NEXT(libdeflate_zlib_decompress_ex);
	int rc = real(d, in, in_n, out, out_n, actual_in, actual_out);
	atomic_fetch_add(&n_ld_zlib_ex, 1);
	if (rc == 0)
		atomic_fetch_add(&b_ld_out, (unsigned long long)(actual_out ? *actual_out : out_n));
	return rc;
}

int libdeflate_deflate_decompress(void *d, const void *in, size_t in_n,
                                  void *out, size_t out_n, size_t *actual_out)
{
	int (*real)(void *, const void *, size_t, void *, size_t, size_t *) =
		NEXT(libdeflate_deflate_decompress);
	int rc = real(d, in, in_n, out, out_n, actual_out);
	atomic_fetch_add(&n_ld_deflate, 1);
	if (rc == 0)
		atomic_fetch_add(&b_ld_out, (unsigned long long)(actual_out ? *actual_out : out_n));
	return rc;
}

__attribute__((destructor)) static void report(void)
{
	const char *path = getenv("MC_CODEC_WITNESS_OUT");
	FILE *f = path ? fopen(path, "w") : stderr;
	if (!f) f = stderr;
	fprintf(f,
	    "{\"zlib_inflate_calls\":%llu,\"zlib_inflateInit_calls\":%llu,"
	    "\"zlib_bytes_out\":%llu,"
	    "\"libdeflate_alloc_decompressor_calls\":%llu,"
	    "\"libdeflate_zlib_decompress_calls\":%llu,"
	    "\"libdeflate_zlib_decompress_ex_calls\":%llu,"
	    "\"libdeflate_deflate_decompress_calls\":%llu,"
	    "\"libdeflate_bytes_out\":%llu}\n",
	    (unsigned long long)n_inflate, (unsigned long long)n_inflateInit,
	    (unsigned long long)b_inflate_out,
	    (unsigned long long)n_ld_alloc, (unsigned long long)n_ld_zlib,
	    (unsigned long long)n_ld_zlib_ex, (unsigned long long)n_ld_deflate,
	    (unsigned long long)b_ld_out);
	if (f != stderr) fclose(f);
}
