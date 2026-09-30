/* Measurement-only sub-timers for the output stage.
 *
 * Active only in a -DTIMING build; compiles to nothing otherwise. The globals
 * are defined in motioncorr_runner.cpp next to MCtimer.
 *
 * Caveat for the tags below: Image::write() is normally reached only from the
 * OutputWriter thread, so each of these totals belongs to one thread and is
 * sound. A synchronous image write on the main thread that overlaps a queued
 * one -- the power spectrum under --grouping_for_ps, say -- would tick the
 * same tags from both, and Timer's accumulation is unsynchronised, so those
 * rows would then under-report. The stage totals in motioncorr_runner.cpp are
 * unaffected: they are ticked from the main thread only. */
#ifndef OUTPUT_TIMING_H_
#define OUTPUT_TIMING_H_

#ifdef TIMING
#include "src/time.h"
extern Timer MCtimer;
extern int TIMING_W_OPEN;
extern int TIMING_W_STATS;
extern int TIMING_W_HEADER;
extern int TIMING_W_PAYLOAD;
extern int TIMING_W_CLOSE;
#define OTIC(label) (MCtimer.tic(label))
#define OTOC(label) (MCtimer.toc(label))
#else
#define OTIC(label)
#define OTOC(label)
#endif

#endif
