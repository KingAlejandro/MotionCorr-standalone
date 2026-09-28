/***************************************************************************
 *
 * Author: "Takanori Nakane"
 * MRC Laboratory of Molecular Biology
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * This complete copyright notice must be included in any revised version of the
 * source code. Additional authorship citations may be added, but existing
 * author citations must be preserved.
 ***************************************************************************/

#ifndef RWTIFF_LAYOUT_H
#define RWTIFF_LAYOUT_H

// Uncomment to trace TIFF reads. This header is included before src/rwTIFF.h,
// so the define has to live here to reach the guarded blocks in both files.
//#define DEBUG_TIFF

// The directory-0 properties of a TIFF movie, and the strip scratch a reader
// decodes through. Split out of readTIFF() so the file-level metadata can be
// resolved once and then shared, read-only, by several independent TIFF
// handles (issue #85 lane B). readTIFF() itself resolves it per call, exactly
// as before; there is one copy of this logic, not two.

/** Reusable strip buffer.
 *
 * Allocated through LibTIFF's own allocator, because that is what readTIFF has
 * always handed to TIFFReadEncodedStrip. Grows only; a reader keeps one for its
 * whole lifetime instead of allocating per frame.
 */
struct TiffStripScratch
{
	tdata_t ptr = nullptr;
	tsize_t size = 0;

	TiffStripScratch() = default;
	TiffStripScratch(const TiffStripScratch&) = delete;
	TiffStripScratch& operator=(const TiffStripScratch&) = delete;
	~TiffStripScratch() { if (ptr) _TIFFfree(ptr); }

	/** Returns false on allocation failure; the caller reports it. */
	bool ensure(tsize_t want)
	{
		if (ptr != nullptr && size >= want) return true;
		if (ptr) _TIFFfree(ptr);
		ptr = _TIFFmalloc(want);
		size = (ptr != nullptr) ? want : 0;
		return ptr != nullptr;
	}
};

/** Everything readTIFF derives from directory 0 before it decodes anything.
 *
 * Every frame of a movie must match it; readTIFFDirectory rechecks each frame
 * against these values, which is the per-frame consistency check readTIFF has
 * always performed.
 */
struct TiffMovieLayout
{
	long int xDim = 0;   // logical pixels per row; twice `width` when packed 4-bit
	long int yDim = 0;
	long int nDim = 0;   // directories in the file
	uint32_t width = 0;  // as recorded in the file
	uint32_t length = 0;
	uint16_t bitsPerSample = 0;
	uint16_t sampleFormat = 0;
	DataType datatype = Unknown_Type;
	bool packed_4bit = false;
	size_t row_bytes = 0;      // bytes backing one decoded row
	bool has_sampling_rate = false;
	RFLOAT sampling_rate = 0;  // A/pixel, applied to both axes
};

/** Resolve the layout from directory 0 and leave the handle on directory 0.
 *
 * Mutates only `layout` and the handle's current directory, so it is safe to
 * call on one handle and then use the result with others opened on the same
 * path. Reports the same errors, with the same text, as the corresponding
 * section of readTIFF.
 */
inline void readTiffLayout(TIFF* ftiff, TiffMovieLayout &layout,
                           const FileName &name, TiffErrorContext* err_ctx)
{
	if (err_ctx) err_ctx->clear();

	uint32_t width, length;
	if (TIFFGetField(ftiff, TIFFTAG_IMAGEWIDTH, &width) != 1 ||
	    TIFFGetField(ftiff, TIFFTAG_IMAGELENGTH, &length) != 1)
	{
		std::string detail = (err_ctx && err_ctx->has_error) ? (": " + err_ctx->last_error) : "";
		REPORT_ERROR(name + ": The input TIFF file does not have the width or height field" + detail + ".");
	}

	uint16_t sampleFormat, bitsPerSample;
	TIFFGetFieldDefaulted(ftiff, TIFFTAG_BITSPERSAMPLE, &bitsPerSample);
	TIFFGetFieldDefaulted(ftiff, TIFFTAG_SAMPLEFORMAT, &sampleFormat);

	// Find the number of frames.
	// TIFFNumberOfDirectories walks the IFD offset chain. If the file is truncated
	// or has corrupted directory structures, LibTIFF reports an error and returns
	// the count reached prior to the corruption. We intercept LibTIFF errors to
	// distinguish legitimate EOF (error count == 0) from truncated/corrupted IFD chains.
	if (err_ctx) err_ctx->clear();
	long int nDim = TIFFNumberOfDirectories(ftiff);
	if (err_ctx && err_ctx->has_error)
	{
		REPORT_ERROR(name + ": Corrupted TIFF directory structure: " + err_ctx->last_error);
	}
	if (nDim <= 0)
	{
		REPORT_ERROR(name + ": No valid TIFF directories found.");
	}
	// and go back to the start
	if (err_ctx) err_ctx->clear();
	if (TIFFSetDirectory(ftiff, 0) == 0 || (err_ctx && err_ctx->has_error))
	{
		std::string detail = (err_ctx && err_ctx->has_error) ? (": " + err_ctx->last_error) : "";
		REPORT_ERROR(name + ": Failed to set TIFF directory 0" + detail);
	}

	long int xDim = width;

	// Detect 4-bit packed TIFFs. This is IMOD's own extension.
	// It is not easy to detect this format. Here we check only the image size.
	// See IMOD's iiTIFFCheck() in libiimod/iitif.c and sizeCanBe4BitK2SuperRes() in libiimod/mrcfiles.c.
	bool packed_4bit = false;
	if (bitsPerSample == 8 && ((width == 5760 && length == 8184)  || (width == 8184  && length == 5760) || // K3 SR: 11520 x 8184
	                           (width == 4092 && length == 11520) || (width == 11520 && length == 4092) ||
	                           (width == 3710 && length == 7676)  || (width == 7676  && length == 3710) || // K2 SR: 7676 x 7420
	                           (width == 3838 && length == 7420)  || (width == 7420  && length == 3838)))
	{
		packed_4bit = true;
		xDim *= 2;
	}

	DataType datatype;

	if (packed_4bit)
	{
		datatype = UHalf;
	}
	else if (bitsPerSample == 8 && sampleFormat == SAMPLEFORMAT_UINT)
	{
		datatype = UChar;
	}
	else if (bitsPerSample == 8 && sampleFormat == SAMPLEFORMAT_INT)
	{
		datatype = SChar;
	}
	else if (bitsPerSample == 16 && sampleFormat == SAMPLEFORMAT_UINT)
	{
		datatype = UShort;
	}
	else if (bitsPerSample == 16 && sampleFormat == SAMPLEFORMAT_INT)
	{
		datatype = SShort;
	}
	else if (bitsPerSample == 32 && sampleFormat == SAMPLEFORMAT_IEEEFP)
	{
		datatype = Float;
	}
	else
	{
		std::cerr << "Unsupported TIFF format in " << name << ": sample format = " << sampleFormat << ", bits per sample = " << bitsPerSample << std::endl;
		REPORT_ERROR("Unsupported TIFF format.\n");
	}

	layout.xDim = xDim;
	layout.yDim = length;
	layout.nDim = nDim;
	layout.width = width;
	layout.length = length;
	layout.bitsPerSample = bitsPerSample;
	layout.sampleFormat = sampleFormat;
	layout.datatype = datatype;
	layout.packed_4bit = packed_4bit;
	// Bytes backing one decoded row. For packed 4-bit data the file reports 8
	// bits per sample but xDim was doubled to the logical pixel count, so a
	// logical pixel occupies 4 bits, not 8.
	layout.row_bytes = packed_4bit ? (size_t)xDim / 2
	                               : (size_t)xDim * bitsPerSample / 8;

	layout.has_sampling_rate = false;
	layout.sampling_rate = 0;
#ifdef DEBUG_TIFF
	std::cout << "TIFF width " << width << ", length " << length << ", nDim " << nDim
	          << ", sample format " << sampleFormat << ", bits per sample " << bitsPerSample
	          << ", packed_4bit " << packed_4bit << std::endl;
#endif
	uint16_t resolutionUnit;
	float xResolution;
	if (TIFFGetField(ftiff, TIFFTAG_RESOLUTIONUNIT, &resolutionUnit) == 1 &&
	    TIFFGetField(ftiff, TIFFTAG_XRESOLUTION, &xResolution) == 1)
	{
		// We don't support anistropic pixel size
		if (resolutionUnit == RESUNIT_INCH)
		{
			layout.has_sampling_rate = true;
			layout.sampling_rate = RFLOAT(2.54E8 / xResolution); // 1 inch = 2.54 cm
		}
		else if (resolutionUnit == RESUNIT_CENTIMETER)
		{
			layout.has_sampling_rate = true;
			layout.sampling_rate = RFLOAT(1.00E8 / xResolution);
		}
#ifdef DEBUG_TIFF
		std::cout << "resolutionUnit = " << resolutionUnit << " xResolution = " << xResolution
		          << " pixel size = " << layout.sampling_rate << std::endl;
#endif
	}
}

#endif
