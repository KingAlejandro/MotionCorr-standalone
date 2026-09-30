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

#ifndef RWTIFF_H
#define RWTIFF_H

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

// I/O prototypes
/** Apply a resolved TIFF movie layout to this image.
  *
  * Sets the header metadata, checks the stack bounds, fixes the dimensions and
  * reserves the pixel buffer, then returns the number of directories the caller
  * should decode into it. Split out of readTIFF so a reader that resolves the
  * layout once, for several handles, still gives every destination image the
  * identical header state.
  * @ingroup TIFF
*/
long int applyTiffLayout(const TiffMovieLayout &layout, long int img_select,
                         bool readdata, bool isStack, const FileName &name)
{
	const long int _xDim = layout.xDim;
	const long int _yDim = layout.yDim;
	long int _zDim = 1;
	long int _nDim = layout.nDim;

	MDMainHeader.setValue(EMDL_IMAGE_DATATYPE, (int)layout.datatype);

	if (layout.has_sampling_rate)
	{
		MDMainHeader.setValue(EMDL_IMAGE_SAMPLINGRATE_X, layout.sampling_rate);
		MDMainHeader.setValue(EMDL_IMAGE_SAMPLINGRATE_Y, layout.sampling_rate);
	}

	// TODO: TIFF is always a stack, isn't it?
	if (isStack)
	{
		_zDim = 1;
		replaceNsize=_nDim;
		std::stringstream Num;
		std::stringstream Num2;
		if (img_select >= (int)_nDim)
		{
			Num  << (img_select + 1);
			Num2 << _nDim;
			REPORT_ERROR((std::string)"readTIFF: Image number " + Num.str() + " exceeds stack size " + Num2.str() + " of image " + name);
		}
	}
	else
		replaceNsize=0;

	// Map the parameters
	if (isStack && img_select==-1)
		_zDim = 1;
	else if(isStack && img_select!=-1)
		_zDim = _nDim = 1;

	data.setDimensions(_xDim, _yDim, _zDim, _nDim);
	// Only reserve the pixel buffer when the pixels are actually wanted. A
	// header-only read reserved the whole stack -- 1.37 GB for a 24-frame
	// 3710x3838 movie -- and the runner does two of those per movie before any
	// frame is read. setDimensions still runs, so XSIZE/YSIZE/NSIZE callers are
	// unaffected. readMRC already allocates inside its own readdata guard.
	if (readdata)
		data.coreAllocateReuse();

	return _nDim;
}

/** Decode one TIFF directory into `frame_dest`, Y-flipped.
  *
  * `frame_dest` must have room for layout.xDim * layout.yDim samples. The
  * handle is left on `img_select`. Strip validation and row placement live
  * here only, so readTIFF and the persistent-handle reader used by issue #85
  * lane B cannot drift apart.
  * @ingroup TIFF
*/
void readTIFFDirectory(TIFF* ftiff, const TiffMovieLayout &layout, long int img_select,
                       T* frame_dest, TiffStripScratch &scratch,
                       const FileName &name, TiffErrorContext* err_ctx)
{
	if (err_ctx) err_ctx->clear();
	if (TIFFSetDirectory(ftiff, img_select) == 0 || (err_ctx && err_ctx->has_error))
	{
		std::string detail = (err_ctx && err_ctx->has_error) ? (": " + err_ctx->last_error) : "";
		REPORT_ERROR(name + ": Failed to select TIFF frame " + integerToString(img_select) + detail);
	}

	// Make sure image property is consistent for all frames
	uint32_t cur_width, cur_length;
	uint16_t cur_sampleFormat, cur_bitsPerSample;

	if (TIFFGetField(ftiff, TIFFTAG_IMAGEWIDTH, &cur_width) != 1 ||
	    TIFFGetField(ftiff, TIFFTAG_IMAGELENGTH, &cur_length) != 1)
	{
		REPORT_ERROR(name + ": The input TIFF file does not have the width or height field.");
	}
	TIFFGetFieldDefaulted(ftiff, TIFFTAG_BITSPERSAMPLE, &cur_bitsPerSample);
	TIFFGetFieldDefaulted(ftiff, TIFFTAG_SAMPLEFORMAT, &cur_sampleFormat);
	if ((cur_width != layout.width) || (cur_length != layout.length) ||
	    (cur_bitsPerSample != layout.bitsPerSample) || (cur_sampleFormat != layout.sampleFormat))
	{
		REPORT_ERROR(name + ": All frames in a TIFF should have same width, height and pixel format.\n");
	}

	tsize_t stripSize = TIFFStripSize(ftiff);
	tstrip_t numberOfStrips = TIFFNumberOfStrips(ftiff);
	if (stripSize <= 0)
		REPORT_ERROR(name + ": Invalid TIFF strip size.");
	// The scratch owns the buffer and frees it when REPORT_ERROR throws past it.
	if (!scratch.ensure(stripSize))
		REPORT_ERROR(name + ": Failed to allocate TIFF strip buffer.");
	tdata_t buf = scratch.ptr;
#ifdef DEBUG_TIFF
	std::cout << "TIFF stripSize=" << stripSize << " numberOfStrips=" << numberOfStrips << std::endl;
#endif
	const size_t row_bytes = layout.row_bytes;
	size_t rows_read = 0;
	for (tstrip_t strip = 0; strip < numberOfStrips; strip++)
	{
		if (err_ctx) err_ctx->clear();
		tsize_t actually_read = TIFFReadEncodedStrip(ftiff, strip, buf, stripSize);
		if (actually_read <= 0 || actually_read > stripSize || row_bytes == 0 ||
		    (size_t)actually_read % row_bytes != 0 || (err_ctx && err_ctx->has_error))
		{
			std::string detail = (err_ctx && err_ctx->has_error) ? (" (" + err_ctx->last_error + ")") : "";
			REPORT_ERROR(name + ": Invalid decoded TIFF strip size" + detail + ".");
		}
#ifdef DEBUG_TIFF
		std::cout << "Reading strip: " << strip << "actually read byte:" << actually_read << std::endl;
#endif
		// A strip always holds whole rows, so convert each one directly into
		// its Y-flipped destination.
		//
		// In an MRC file, the origin is bottom-left, +X to the right, +Y to the top.
		// (c.f. Fig. 2 of Heymann et al, JSB 2005 https://doi.org/10.1016/j.jsb.2005.06.001
		// IMOD's interpretation http://bio3d.colorado.edu/imod/doc/mrc_format.txt)
		// 3dmod (from IMOD) and e2display.py (from EMAN2) display like this.
		//
		// relion_display has the origin at top-left, +X to the right, +Y to the bottom.
		// GIMP and ImageJ display in this way as well.
		// A TIFF file, with TIFFTAG_ORIENTATION = 1 (default), shares this convention.
		//
		// So, the origin and the direction of the Y axis are the opposite between MRC and TIFF.
		// IMOD, EMAN2, SerialEM and MotionCor2 flip the Y axis whenever they read or write a TIFF file.
		// We follow this; applying the flip per row here produces the same image
		// as the separate reversing pass it replaces.
		const size_t first_row = rows_read;
		const size_t n_rows = (size_t)actually_read / row_bytes;
		if (first_row > (size_t)layout.yDim || n_rows > (size_t)layout.yDim - first_row)
		{
			REPORT_ERROR(name + ": Decoded TIFF strips exceed the frame height.");
		}
		for (size_t r = 0; r < n_rows; r++)
		{
			const size_t dest_row = layout.yDim - 1 - (first_row + r);
			castPage2T((char*)buf + r * row_bytes,
			           frame_dest + dest_row * layout.xDim,
			           layout.datatype, layout.xDim);
		}
		rows_read += n_rows;
	}

	if (rows_read != (size_t)layout.yDim)
		REPORT_ERROR(name + ": Decoded TIFF strips do not fill the frame.");
}

/** Decode one frame through a caller-owned, already-open TIFF handle.
  *
  * Equivalent to read(name, true, img_select, false, true) on a TIFF, with the
  * open/close lifecycle and the layout resolution lifted out to the caller so
  * they can be done once per movie instead of once per frame. The handle, the
  * error context and the scratch must belong to the calling thread alone.
  *
  * Used by TiffMovieReader (issue #85 lane B). Nothing else calls it.
  * @ingroup TIFF
*/
void readTIFFFrameFromHandle(TIFF* ftiff, const TiffMovieLayout &layout, long int img_select,
                             TiffStripScratch &scratch, const FileName &name,
                             TiffErrorContext* err_ctx)
{
	// The prologue Image::_read runs before dispatching to readTIFF. fimg and
	// fhed are what _read copies out of a TIFF-only fImageHandler: both null.
	dataflag = 1;
	mmapOn = false;
	fimg = NULL;
	fhed = NULL;
	filename = name;
	MDMainHeader.clear();
	MDMainHeader.addObject();

	if (!err_ctx)
		err_ctx = g_tls_tiff_error_context;
	TiffErrorScope scope(err_ctx);

	applyTiffLayout(layout, img_select, true, true, name);
	readTIFFDirectory(ftiff, layout, img_select, MULTIDIM_ARRAY(data), scratch, name, err_ctx);
}

/** TIFF Reader
  * @ingroup TIFF
*/
int readTIFF(TIFF* ftiff, long int img_select, bool readdata=false, bool isStack=false, const FileName &name="", TiffErrorContext* err_ctx=nullptr)
{
// DEBUG_TIFF is defined (commented out) at the top of src/rwTIFF_layout.h,
// which is included before this file, so that one switch reaches every
// guarded block in both.
#ifdef DEBUG_TIFF
	printf("DEBUG readTIFF: Reading TIFF file. img_select %d\n", img_select);
#endif

	if (!err_ctx)
		err_ctx = g_tls_tiff_error_context;
	TiffErrorScope scope(err_ctx);

	TiffMovieLayout layout;
	readTiffLayout(ftiff, layout, name, err_ctx);

#ifdef DEBUG_TIFF
	printf("TIFF width %d, length %d, nDim %d, sample format %d, bits per sample %d\n",
	       layout.width, layout.length, (int)layout.nDim, layout.sampleFormat, layout.bitsPerSample);
#endif

	const long int n_to_read = applyTiffLayout(layout, img_select, readdata, isStack, name);

	if (readdata)
	{
		if (img_select == -1) img_select = 0; // img_select starts from 0

		// One buffer for the whole call, grown on demand, instead of one
		// allocation per directory.
		TiffStripScratch scratch;
		for (long int i = 0; i < n_to_read; i++)
		{
			readTIFFDirectory(ftiff, layout, img_select,
			                  MULTIDIM_ARRAY(data) + (size_t)i * layout.xDim * layout.yDim,
			                  scratch, name, err_ctx);
			img_select++;
		}
	}

	return 0;
}

#endif
