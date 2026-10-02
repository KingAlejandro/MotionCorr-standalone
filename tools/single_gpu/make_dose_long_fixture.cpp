// Explicit synthetic long movies: cycle decoded tutorial frames. Not new
// acquisition/scientific data. TIFF encoding is identical between timed arms.
#include <tiffio.h>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>
int main(int argc,char**argv) {
 if(argc!=4){std::cerr<<"input output frames\n";return 1;}
 try {
 const int frames=std::stoi(argv[3]);
 if(frames!=8&&frames!=24&&frames!=80&&frames!=160) throw std::runtime_error("unsupported frame count");
 TIFF*in=TIFFOpen(argv[1],"r"); if(!in)throw std::runtime_error("input open");
 std::vector<std::vector<uint16_t>> pages; uint32_t nx=0,ny=0;
 do {
  uint32_t x,y;uint16_t bits=0,samples=0,format=SAMPLEFORMAT_UINT;
  TIFFGetField(in,TIFFTAG_IMAGEWIDTH,&x);TIFFGetField(in,TIFFTAG_IMAGELENGTH,&y);
  TIFFGetFieldDefaulted(in,TIFFTAG_BITSPERSAMPLE,&bits);TIFFGetFieldDefaulted(in,TIFFTAG_SAMPLESPERPIXEL,&samples);TIFFGetFieldDefaulted(in,TIFFTAG_SAMPLEFORMAT,&format);
  if(bits!=16||samples!=1||format!=SAMPLEFORMAT_UINT||TIFFScanlineSize(in)!=(tmsize_t)x*2)throw std::runtime_error("uint16 grayscale input required");
  if(pages.empty()){nx=x;ny=y;}else if(x!=nx||y!=ny)throw std::runtime_error("mixed input geometry");
  pages.emplace_back((size_t)x*y);
  for(uint32_t r=0;r<y;++r)if(TIFFReadScanline(in,pages.back().data()+(size_t)r*x,r,0)<0)throw std::runtime_error("input scanline");
 }while(TIFFReadDirectory(in));
 TIFFClose(in);if(pages.size()!=24)throw std::runtime_error("source must have24pages");
 TIFF*out=TIFFOpen(argv[2],"w8");if(!out)throw std::runtime_error("output open");
 for(int f=0;f<frames;++f){
  TIFFSetField(out,TIFFTAG_IMAGEWIDTH,nx);TIFFSetField(out,TIFFTAG_IMAGELENGTH,ny);
  TIFFSetField(out,TIFFTAG_BITSPERSAMPLE,16);TIFFSetField(out,TIFFTAG_SAMPLESPERPIXEL,1);
  TIFFSetField(out,TIFFTAG_SAMPLEFORMAT,SAMPLEFORMAT_UINT);TIFFSetField(out,TIFFTAG_PHOTOMETRIC,PHOTOMETRIC_MINISBLACK);
  TIFFSetField(out,TIFFTAG_PLANARCONFIG,PLANARCONFIG_CONTIG);TIFFSetField(out,TIFFTAG_COMPRESSION,COMPRESSION_ADOBE_DEFLATE);
  TIFFSetField(out,TIFFTAG_PREDICTOR,1);TIFFSetField(out,TIFFTAG_ROWSPERSTRIP,1);TIFFSetField(out,TIFFTAG_ZIPQUALITY,1);
  for(uint32_t r=0,s=0;r<ny;r+=1,++s){uint32_t rows=1;
   if(TIFFWriteEncodedStrip(out,s,pages[f%24].data()+(size_t)r*nx,(tmsize_t)rows*nx*2)<0)throw std::runtime_error("output strip");}
  if(!TIFFWriteDirectory(out))throw std::runtime_error("output directory");
 }
 TIFFClose(out);
 // Round-trip all pages; compare decoded values, not only header page counts.
 TIFF*check=TIFFOpen(argv[2],"r");if(!check)throw std::runtime_error("roundtrip open");
 std::vector<uint16_t> row(nx);int f=0;
 do {
  uint32_t rows;uint16_t comp;TIFFGetField(check,TIFFTAG_ROWSPERSTRIP,&rows);TIFFGetField(check,TIFFTAG_COMPRESSION,&comp);
  if(rows!=1||comp!=COMPRESSION_ADOBE_DEFLATE)throw std::runtime_error("encoding contract");
  if(f>=frames)throw std::runtime_error("extra output page");
  for(uint32_t r=0;r<ny;++r){if(TIFFReadScanline(check,row.data(),r,0)<0)throw std::runtime_error("roundtrip scanline");
   for(uint32_t c=0;c<nx;++c)if(row[c]!=pages[f%24][(size_t)r*nx+c])throw std::runtime_error("roundtrip bytes");}
  ++f;
 }while(TIFFReadDirectory(check));TIFFClose(check);if(f!=frames)throw std::runtime_error("missing output page");
 std::cout<<"PASS synthetic cycle source24 frames="<<frames<<" geometry="<<nx<<"x"<<ny<<" rowsperstrip1 predictor1 deflate1\n";
 }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}
}
