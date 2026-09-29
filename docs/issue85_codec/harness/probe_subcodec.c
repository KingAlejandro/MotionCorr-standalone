#include <stdio.h>
#include <tiffio.h>

/* Probe: is this LibTIFF able to use libdeflate for the Deflate codec?
 * TIFFTAG_DEFLATE_SUBCODEC is only settable to DEFLATE_SUBCODEC_LIBDEFLATE
 * when LibTIFF was built with libdeflate support. */
int main(int argc, char **argv)
{
	const char *path = (argc > 1) ? argv[1] : "probe_subcodec.tif";
	int ok = 0;
	TIFFSetErrorHandler(0);
	TIFFSetWarningHandler(0);
#ifdef DEFLATE_SUBCODEC_LIBDEFLATE
	TIFF *tif = TIFFOpen(path, "w");
	if (tif) {
		if (TIFFSetField(tif, TIFFTAG_COMPRESSION, COMPRESSION_ADOBE_DEFLATE) == 1)
			ok = TIFFSetField(tif, TIFFTAG_DEFLATE_SUBCODEC,
			                  DEFLATE_SUBCODEC_LIBDEFLATE) == 1;
		TIFFClose(tif);
	}
#endif
	printf("libdeflate_subcodec=%d version=%s\n", ok, TIFFGetVersion());
	return ok ? 0 : 1;
}
