// Lifecycle and admission tests for the bounded next-movie prefetch (issue #94).
//
// These are the cheap checks that gate the prototype: every one of them runs in
// well under a second and needs no GPU. Only the automatic-budget control
// touches the filesystem, and only because resolveBudgetBytes probes files for
// real -- with unreadable names every queue capacity hits the same fallback
// and the control observes nothing. It cleans up after itself. They exist
// because the interesting failures here -- an early budget release, a double
// release, a producer left asleep on the resource that was not cancelled -- are
// invisible to an end-to-end output comparison, which would simply pass.
//
// Every blocking case runs under a watchdog, so a deadlock fails the test
// instead of hanging the suite. A test that can only hang is not a test.

#include "src/movie_prefetch.h"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <system_error>
#include <unistd.h>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using movieio::ByteBudget;
using movieio::BoundedQueue;
using movieio::MovieGeometry;
using movieio::MoviePrefetchRecord;
using movieio::MoviePrefetcher;

namespace
{

int failures = 0;

void check(bool condition, const std::string &what)
{
	if (condition) return;
	std::cerr << "FAIL: " << what << std::endl;
	failures++;
}

// Kills the process if the guarded section overruns. std::_Exit avoids running
// destructors of a deadlocked program, which could themselves block.
class Watchdog
{
public:
	Watchdog(double seconds, std::string what) : what_(std::move(what))
	{
		thread_ = std::thread([this, seconds] {
			std::unique_lock<std::mutex> lock(mutex_);
			if (!cv_.wait_for(lock, std::chrono::duration<double>(seconds),
			                  [this] { return done_; }))
			{
				std::fprintf(stderr, "FAIL: watchdog fired, deadlock in: %s\n", what_.c_str());
				std::fflush(stderr);
				std::_Exit(3);
			}
		});
	}
	~Watchdog()
	{
		{
			std::lock_guard<std::mutex> lock(mutex_);
			done_ = true;
		}
		cv_.notify_all();
		thread_.join();
	}

private:
	std::string what_;
	std::mutex mutex_;
	std::condition_variable cv_;
	bool done_ = false;
	std::thread thread_;
};

// One synthetic "movie unit": a geometry whose estimate is predictable.
constexpr int kNx = 256, kNy = 256, kNFrames = 4, kIoThreads = 1;

size_t unitBytes()
{
	return movieio::estimateDecodedMovieBytes(kNx, kNy, kNFrames, kIoThreads);
}

MoviePrefetcher::Options unitOptions(size_t units, size_t queue_capacity = 1)
{
	MoviePrefetcher::Options options;
	options.budget_bytes = unitBytes() * units;
	options.queue_capacity = queue_capacity;
	options.n_io_threads = kIoThreads;
	options.first_frame_sum = 1;
	options.last_frame_sum = -1;
	return options;
}

// Writes a minimal real MRC float32 stack. resolveBudgetBytes probes files for
// real, so the automatic-budget control below needs something it can actually
// read: with unreadable names every capacity falls through to the same
// hardcoded fallback and the test would pass without observing anything.
void writeTinyMrcStack(const std::string &path, int nx, int ny, int nz)
{
	std::vector<char> header(1024, 0);
	auto put_i32 = [&](size_t off, int32_t v) { std::memcpy(header.data() + off, &v, 4); };
	auto put_f32 = [&](size_t off, float v) { std::memcpy(header.data() + off, &v, 4); };
	put_i32(0, nx); put_i32(4, ny); put_i32(8, nz);
	put_i32(12, 2);                                  // mode 2 = float32
	put_i32(28, nx); put_i32(32, ny); put_i32(36, nz);
	put_f32(40, (float)nx); put_f32(44, (float)ny); put_f32(48, (float)nz);
	put_f32(52, 90.0f); put_f32(56, 90.0f); put_f32(60, 90.0f);
	put_i32(64, 1); put_i32(68, 2); put_i32(72, 3);
	put_f32(76, 0.0f); put_f32(80, 1.0f); put_f32(84, 0.5f);
	std::memcpy(header.data() + 208, "MAP ", 4);
	put_i32(212, 0x00004144);

	std::ofstream out(path, std::ios::binary);
	out.write(header.data(), (std::streamsize)header.size());
	const std::vector<float> plane((size_t)nx * ny, 0.5f);
	for (int n = 0; n < nz; n++)
		out.write(reinterpret_cast<const char *>(plane.data()),
		          (std::streamsize)(plane.size() * sizeof(float)));
	if (!out) { std::cerr << "FAIL: could not write fixture " << path << std::endl; failures++; }
}

// Temp directory that cleans up after itself, so the suite leaves no litter.
class TempDir
{
public:
	TempDir()
	{
		path_ = std::filesystem::temp_directory_path() /
		        ("mc94_lifecycle_" + std::to_string(::getpid()));
		std::error_code ec;
		std::filesystem::create_directories(path_, ec);
	}
	~TempDir()
	{
		std::error_code ec;
		std::filesystem::remove_all(path_, ec);
	}
	std::string file(const std::string &name) const { return (path_ / name).string(); }

private:
	std::filesystem::path path_;
};

std::vector<FileName> movieNames(int count, const char *ext = ".mrcs")
{
	std::vector<FileName> names;
	for (int i = 0; i < count; i++) names.push_back(FileName("movie" + std::to_string(i) + ext));
	return names;
}

// ---------------------------------------------------------------------------

void testSizeArithmetic()
{
	check(movieio::roundUpToPage(0) == 0, "roundUpToPage(0) is 0");
	check(movieio::roundUpToPage(1) == movieio::kPageBytes, "roundUpToPage rounds up");
	check(movieio::roundUpToPage(movieio::kPageBytes) == movieio::kPageBytes,
	      "roundUpToPage leaves an exact page alone");

	const size_t max = (size_t)-1;
	check(movieio::saturatingMul(max, 2) == max, "saturatingMul saturates instead of wrapping");
	check(movieio::saturatingAdd(max, 2) == max, "saturatingAdd saturates instead of wrapping");
	check(movieio::saturatingMul(0, max) == 0, "saturatingMul handles zero");

	// A geometry whose pixel count alone overflows must not produce a small
	// estimate; under-charging is the one direction that breaks the bound.
	const size_t huge = movieio::estimateDecodedMovieBytes(2000000000, 2000000000, 64, 8);
	check(huge == max, "an overflowing geometry saturates rather than wrapping small");

	// The estimate charges more than the raw pixel array: frames, per-frame
	// overhead and decoder scratch.
	const size_t raw = (size_t)kNx * kNy * sizeof(float) * kNFrames;
	check(unitBytes() > raw, "the estimate exceeds the bare pixel arrays");
	check(movieio::estimateDecodedMovieBytes(kNx, kNy, kNFrames, 4) >
	      movieio::estimateDecodedMovieBytes(kNx, kNy, kNFrames, 1),
	      "more IO threads charge more decoder scratch");
	check(movieio::estimateDecodedMovieBytes(kNx, kNy, 0, 1) == 0,
	      "a movie with no selected frames costs nothing");
}

void testBudgetBasics()
{
	ByteBudget budget(1000);
	check(budget.tooLargeForBudget(1001), "a request above the limit can never be admitted");
	check(!budget.tooLargeForBudget(1000), "an exactly-fitting request is admissible");

	{
		ByteBudget::Reservation exact = budget.reserve(1000);
		check(exact.held(), "exact fit is granted");
		check(budget.reservedBytes() == 1000, "reserved bytes are charged");
		ByteBudget::Reservation impossible = budget.reserve(1001);
		check(!impossible.held(), "an over-limit request returns an unheld reservation");
		check(budget.reservedBytes() == 1000, "a refused request charges nothing");
	}
	check(budget.reservedBytes() == 0, "the reservation is returned when it is destroyed");
	check(budget.peakReservedBytes() == 1000, "the peak survives the release");

	// Move transfers ownership: exactly one of the two handles owes bytes.
	{
		ByteBudget::Reservation a = budget.reserve(400);
		ByteBudget::Reservation b = std::move(a);
		check(!a.held() && b.held(), "moving transfers the claim");
		check(budget.reservedBytes() == 400, "a move does not double-charge");
		a.release();
		check(budget.reservedBytes() == 400, "releasing a moved-from handle returns nothing");
		b.release();
		check(budget.reservedBytes() == 0, "releasing the owner returns the bytes");
		b.release();
		check(budget.reservedBytes() == 0, "a second release is a no-op, not a double return");
	}

	// Move assignment must release what the target already held.
	{
		ByteBudget::Reservation a = budget.reserve(300);
		ByteBudget::Reservation b = budget.reserve(200);
		check(budget.reservedBytes() == 500, "two live reservations are both charged");
		a = std::move(b);
		check(budget.reservedBytes() == 200, "move-assignment releases the overwritten claim");
	}
	check(budget.reservedBytes() == 0, "everything is returned at scope exit");
}

void testBudgetBlocksAndWakes()
{
	Watchdog dog(10.0, "budget blocks then wakes on release");
	ByteBudget budget(1000);
	ByteBudget::Reservation held = budget.reserve(800);
	check(held.held(), "first reservation granted");

	std::atomic<bool> granted{false};
	std::thread waiter([&] {
		ByteBudget::Reservation second = budget.reserve(400); // needs 200 back
		granted = second.held();
	});

	// The waiter must still be blocked: 800 + 400 > 1000.
	std::this_thread::sleep_for(std::chrono::milliseconds(50));
	check(!granted.load(), "a request that does not fit blocks instead of over-committing");
	check(budget.reservedBytes() == 800, "the blocked request charges nothing while it waits");

	held.release();
	waiter.join();
	check(granted.load(), "releasing bytes wakes the blocked request");
	check(budget.blockedSeconds() > 0.0, "the blocked interval is recorded");
	check(budget.reservedBytes() == 0, "the woken reservation is returned at scope exit");
}

void testBudgetCancelWakesWaiter()
{
	Watchdog dog(10.0, "cancel wakes a blocked reserve");
	ByteBudget budget(1000);
	ByteBudget::Reservation held = budget.reserve(1000);

	std::atomic<bool> finished{false}, got{false};
	std::thread waiter([&] {
		ByteBudget::Reservation second = budget.reserve(500);
		got = second.held();
		finished = true;
	});
	std::this_thread::sleep_for(std::chrono::milliseconds(50));
	check(!finished.load(), "the waiter is genuinely blocked before cancellation");

	budget.cancel();
	waiter.join();
	check(finished.load(), "cancel unblocks the waiter");
	check(!got.load(), "a cancelled reserve returns an unheld reservation");
}

void testForcedGrant()
{
	ByteBudget budget(1000);
	{
		ByteBudget::Reservation forced = budget.reserveForced(4000);
		check(forced.held(), "a forced grant is always granted");
		check(budget.reservedBytes() == 4000, "the forced grant is charged, not hidden");
		check(budget.overBudgetGrants() == 1, "an override that really exceeds is counted");
		check(budget.peakReservedBytes() >= 4000, "the peak shows the override");
	}
	check(budget.reservedBytes() == 0, "a forced grant is returned like any other");

	// A forced grant that fits is NOT an override. An in-line load happens for
	// unsupported formats too, and counting those would make the field answer
	// "how many in-line loads" instead of "was the bound broken".
	{
		ByteBudget::Reservation fits = budget.reserveForced(100);
		check(fits.held(), "a small forced grant is granted");
		check(budget.overBudgetGrants() == 1, "a grant that fits does not count as an override");
	}
	// And one that fits only because nothing else is held still counts when it
	// is taken on top of an existing charge.
	{
		ByteBudget::Reservation held = budget.reserve(900);
		ByteBudget::Reservation tips = budget.reserveForced(200); // 1100 > 1000
		check(budget.overBudgetGrants() == 2, "a grant that tips the total over is counted");
	}
	check(budget.reservedBytes() == 0, "everything returns");
}

// The record must free its frames BEFORE returning their bytes. A defaulted
// destructor returns the budget in reverse declaration order, which would wake
// a blocked producer while these buffers are still being freed: real resident
// memory then transiently reaches limit + one movie on a host sized to limit,
// and no counter ever shows it because the accounting is already back to zero.
void testRecordFreesFramesBeforeReturningBytes()
{
	Watchdog dog(10.0, "record destruction order");
	ByteBudget budget(unitBytes() * 2);
	{
		MoviePrefetchRecord record;
		record.reservation = budget.reserve(unitBytes());
		record.Iframes.resize(kNFrames);
		for (int i = 0; i < kNFrames; i++) record.Iframes[i]().resize(kNy, kNx);
		check(record.reservation.held(), "the record holds its reservation");
		check(budget.reservedBytes() == unitBytes(), "and the bytes are charged");
	}
	check(budget.reservedBytes() == 0, "destruction returns the bytes exactly once");

	// The ordering itself is enforced by the explicit destructor rather than by
	// member order, so that reordering members cannot silently reintroduce the
	// overshoot. Check the destructor really is the thing doing it: after an
	// explicit release the frames must still be intact and freeable.
	{
		MoviePrefetchRecord record;
		record.reservation = budget.reserve(unitBytes());
		record.Iframes.resize(kNFrames);
		record.reservation.release();
		check(budget.reservedBytes() == 0, "an explicit release still returns once");
		check(record.Iframes.size() == (size_t)kNFrames,
		      "releasing the budget does not touch the buffers");
	}
	check(budget.reservedBytes() == 0, "no double return from the destructor afterwards");
}

// A movie whose header reports a nonpositive geometry must not be admitted for
// free. Returning a zero estimate would let it decode entirely off-budget.
void testDegenerateGeometryIsNotFree()
{
	const size_t max = (size_t)-1;
	check(movieio::estimateDecodedMovieBytes(0, kNy, kNFrames, 1) == max,
	      "a zero width with frames to read is charged the maximum, not zero");
	check(movieio::estimateDecodedMovieBytes(kNx, -1, kNFrames, 1) == max,
	      "a negative height with frames to read is charged the maximum, not zero");
	check(movieio::estimateDecodedMovieBytes(0, 0, 0, 1) == 0,
	      "but no selected frames really does allocate nothing");

	ByteBudget budget(unitBytes());
	check(budget.tooLargeForBudget(movieio::estimateDecodedMovieBytes(0, kNy, kNFrames, 1)),
	      "so such a movie falls back instead of being admitted");
}

void testBoundedQueue()
{
	Watchdog dog(10.0, "bounded queue push/pop/finish/cancel");
	{
		BoundedQueue<int> queue(2);
		int out = -1;
		// Two statements, not `a && b`: short-circuiting would skip the second
		// push entirely if the first ever failed.
		check(queue.push(1), "first push within capacity succeeds");
		check(queue.push(2), "second push within capacity succeeds");
		check(queue.size() == 2, "occupancy is visible");
		check(queue.pop(out) && out == 1, "pop is FIFO");
		check(queue.pop(out) && out == 2, "pop is FIFO");
		queue.finish();
		check(!queue.pop(out), "a finished, drained queue reports exhaustion");
		check(queue.peakOccupancy() == 2, "the peak occupancy is retained");
	}
	{
		// A full queue blocks the producer until the consumer takes one.
		BoundedQueue<int> queue(1);
		check(queue.push(1), "first push fits");
		std::atomic<bool> pushed{false};
		std::thread producer([&] { pushed = queue.push(2); });
		std::this_thread::sleep_for(std::chrono::milliseconds(50));
		check(!pushed.load(), "a full queue blocks the producer");
		int out = -1;
		check(queue.pop(out) && out == 1, "the consumer drains one");
		producer.join();
		check(pushed.load(), "the blocked push completes once a slot frees");
	}
	{
		// Cancel must wake both ends.
		BoundedQueue<int> queue(1);
		check(queue.push(1), "prime the queue");
		std::atomic<bool> done{false}, result{true};
		std::thread producer([&] { result = queue.push(2); done = true; });
		std::this_thread::sleep_for(std::chrono::milliseconds(50));
		check(!done.load(), "producer is blocked on a full queue");
		queue.cancel();
		producer.join();
		check(!result.load(), "a cancelled push reports failure and keeps the item");
		int out = -1;
		check(!queue.pop(out), "a cancelled queue does not hand out items");
	}
	{
		// Cancelling a queue holding reservations must return their bytes.
		ByteBudget budget(1000);
		{
			BoundedQueue<ByteBudget::Reservation> queue(2);
			check(queue.push(budget.reserve(300)), "queued reservation 1");
			check(queue.push(budget.reserve(300)), "queued reservation 2");
			check(budget.reservedBytes() == 600, "queued items still own their bytes");
			queue.cancel();
			check(budget.reservedBytes() == 0, "cancellation drains and returns the bytes");
		}
	}
}

// ---------------------------------------------------------------------------
// Producer/consumer lifecycle with a synthetic loader
// ---------------------------------------------------------------------------

struct FakeLoader
{
	int nx = kNx, ny = kNy, nn = kNFrames;
	double decode_seconds = 0.0;
	long throw_on_index = -1;   // -1 = never
	std::atomic<long> probes{0};
	std::atomic<long> decodes{0};

	MovieGeometry probe(const FileName &fn) const
	{
		MovieGeometry geometry;
		geometry.nx = nx;
		geometry.ny = ny;
		geometry.nn = nn;
		return geometry;
	}

	void install(MoviePrefetcher &prefetcher)
	{
		prefetcher.setProbeForTesting([this](const FileName &fn) {
			probes++;
			return probe(fn);
		});
		prefetcher.setLoaderForTesting(
			[this](const FileName &fn, MoviePrefetchRecord &record, int) {
				if (record.index == throw_on_index)
					throw std::runtime_error("synthetic decode failure: " + std::string(fn));
				if (decode_seconds > 0.0)
					std::this_thread::sleep_for(std::chrono::duration<double>(decode_seconds));
				record.Iframes.resize(record.frames.size());
				decodes++;
			});
	}
};

void testOrderingAndCompletion()
{
	Watchdog dog(30.0, "producer publishes every movie in order");
	const int n = 6;
	MoviePrefetcher prefetcher(movieNames(n), unitOptions(3));
	FakeLoader loader;
	loader.install(prefetcher);
	prefetcher.start();

	for (int i = 0; i < n; i++)
	{
		MoviePrefetchRecord record;
		check(prefetcher.next(record), "a record is published for movie " + std::to_string(i));
		check(record.index == i, "records arrive in movie order");
		check(record.mode == MoviePrefetchRecord::Mode::Decoded, "the movie was decoded ahead");
		check((int)record.Iframes.size() == kNFrames, "every selected frame is present");
		check(record.reservation.held(), "the record carries its byte reservation");
	}
	MoviePrefetchRecord trailing;
	check(!prefetcher.next(trailing), "the list is exhausted exactly once");
	check(prefetcher.budget().reservedBytes() == 0, "no bytes are left charged at the end");
	check(loader.decodes.load() == n, "every movie was decoded exactly once");
}

void testAccountingBound()
{
	Watchdog dog(60.0, "active + queued + producer-current stays within the budget");
	const int n = 12;
	// Three units is exactly producer-current + one queued + consumer-active.
	MoviePrefetcher prefetcher(movieNames(n), unitOptions(3));
	FakeLoader loader;
	loader.decode_seconds = 0.002;
	loader.install(prefetcher);
	prefetcher.start();

	const size_t limit = prefetcher.budget().limitBytes();
	size_t observed_peak = 0;
	for (int i = 0; i < n; i++)
	{
		MoviePrefetchRecord record;
		check(prefetcher.next(record), "record " + std::to_string(i) + " arrives");
		// Sample while this record is still held: the producer may be decoding
		// another and a third may be queued.
		for (int sample = 0; sample < 20; sample++)
		{
			const size_t reserved = prefetcher.budget().reservedBytes();
			if (reserved > observed_peak) observed_peak = reserved;
			check(reserved <= limit, "reserved bytes never exceed the budget");
			std::this_thread::sleep_for(std::chrono::microseconds(200));
		}
	}
	check(prefetcher.budget().peakReservedBytes() <= limit,
	      "the recorded peak never exceeded the budget");
	// Control: if the pipeline never actually held more than the consumer's own
	// movie, the bound above would be satisfied trivially and prove nothing.
	check(observed_peak > unitBytes(),
	      "CONTROL: more than one movie really was in flight, so the bound is not vacuous");
	check(prefetcher.budget().overBudgetGrants() == 0, "no override was needed");
}

void testBlockedBudgetStillCompletes()
{
	Watchdog dog(30.0, "a budget of one movie still completes in order");
	const int n = 5;
	// One unit: the consumer's movie alone fills the budget, so the producer is
	// blocked for essentially the whole run. It must still finish, in order.
	MoviePrefetcher prefetcher(movieNames(n), unitOptions(1));
	FakeLoader loader;
	loader.install(prefetcher);
	prefetcher.start();

	for (int i = 0; i < n; i++)
	{
		MoviePrefetchRecord record;
		check(prefetcher.next(record), "record " + std::to_string(i) + " arrives under pressure");
		check(record.index == i, "order is preserved under backpressure");
		check(record.mode == MoviePrefetchRecord::Mode::Decoded, "the movie still gets decoded");
		check(prefetcher.budget().reservedBytes() <= prefetcher.budget().limitBytes(),
		      "the one-movie budget is respected");
	}
	check(prefetcher.budget().blockedSeconds() > 0.0,
	      "CONTROL: the producer really did block, so this case exercised backpressure");
}

void testOversizedMovieFallsBackInline()
{
	Watchdog dog(30.0, "an oversized movie falls back to an in-line load");
	MoviePrefetcher prefetcher(movieNames(3), unitOptions(3));
	FakeLoader loader;
	loader.nx = 8192; // far larger than three 256x256 units
	loader.ny = 8192;
	loader.install(prefetcher);
	prefetcher.start();

	for (int i = 0; i < 3; i++)
	{
		MoviePrefetchRecord record;
		check(prefetcher.next(record), "a marker is still published for movie " + std::to_string(i));
		check(record.mode == MoviePrefetchRecord::Mode::LoadInline,
		      "a movie larger than the whole budget is not admitted");
		check(record.Iframes.empty(), "no frames were decoded for it");
		check(!record.reservation.held(), "and no bytes were reserved for it");
	}
	check(loader.decodes.load() == 0, "the producer never decoded an inadmissible movie");
	check(prefetcher.stats().inline_loaded == 3, "the fallbacks are counted");
	check(prefetcher.stats().over_budget_grants == 0,
	      "and no override has happened yet: the producer reserved nothing");

	// The consumer's own in-line load is charged through a counted forced grant.
	{
		ByteBudget::Reservation forced = prefetcher.reserveInline(unitBytes() * 10);
		check(forced.held(), "the consumer's in-line load is granted");
		check(prefetcher.budget().reservedBytes() > prefetcher.budget().limitBytes(),
		      "and is visible as an over-budget grant rather than untracked");
	}
	check(prefetcher.stats().over_budget_grants == 1, "the override is reported");
}

void testUnsupportedFormatFallsBackInline()
{
	Watchdog dog(30.0, "EER and compressed MRC route to the in-line loader");
	std::vector<FileName> movies = {FileName("a.eer"), FileName("b.mrc.bz2"),
	                                FileName("c.mrcs.zst"), FileName("d.mrcs")};
	MoviePrefetcher prefetcher(movies, unitOptions(3));
	FakeLoader loader;
	loader.install(prefetcher);
	prefetcher.start();

	for (size_t i = 0; i < movies.size(); i++)
	{
		MoviePrefetchRecord record;
		check(prefetcher.next(record), "a record arrives for " + std::string(movies[i]));
		const bool expect_inline = (i < 3);
		check(record.mode == (expect_inline ? MoviePrefetchRecord::Mode::LoadInline
		                                    : MoviePrefetchRecord::Mode::Decoded),
		      "format routing for " + std::string(movies[i]));
	}
	check(loader.probes.load() == 1, "unsupported formats are not even probed by the producer");
}

void testProducerErrorIsMovieTagged()
{
	Watchdog dog(30.0, "a decode error is a per-movie outcome");
	const int n = 4;
	MoviePrefetcher prefetcher(movieNames(n), unitOptions(3));
	FakeLoader loader;
	loader.throw_on_index = 1;
	loader.install(prefetcher);
	prefetcher.start();

	for (int i = 0; i < n; i++)
	{
		MoviePrefetchRecord record;
		check(prefetcher.next(record), "record " + std::to_string(i) + " arrives");
		if (i == 1)
		{
			check(record.mode == MoviePrefetchRecord::Mode::Failed, "the bad movie is tagged failed");
			check(record.error != nullptr, "its exception travels with the record");
			check(!record.reservation.held(),
			      "its bytes were returned when the partial frames were dropped");
			bool rethrown = false;
			try { std::rethrow_exception(record.error); }
			catch (const std::runtime_error &) { rethrown = true; }
			catch (...) {}
			check(rethrown, "the original exception type survives the handoff");
		}
		else
		{
			check(record.mode == MoviePrefetchRecord::Mode::Decoded,
			      "healthy movies around the failure are still decoded");
		}
	}
	check(prefetcher.stats().failed == 1 && prefetcher.stats().decoded == 3,
	      "the failure is counted once and does not abort the batch");
	check(prefetcher.budget().reservedBytes() == 0, "the failed movie leaked no bytes");
}

void testCancelWhileProducerBlockedOnBudget()
{
	Watchdog dog(30.0, "cancel while the producer waits for memory");
	MoviePrefetcher prefetcher(movieNames(20), unitOptions(1));
	FakeLoader loader;
	loader.install(prefetcher);
	prefetcher.start();

	MoviePrefetchRecord held;
	check(prefetcher.next(held), "hold the only unit of budget");
	std::this_thread::sleep_for(std::chrono::milliseconds(100));
	// Establish the precondition rather than assuming it: the producer must
	// actually be asleep on the budget, otherwise cancelAndJoin() returning
	// proves nothing. Without this the case passes identically against a
	// producer that had already exited.
	check(prefetcher.budget().reservedBytes() == held.reservation.bytes(),
	      "CONTROL: the consumer's movie is the only thing charged, so the producer "
	      "cannot have reserved anything");
	check(prefetcher.stats().decoded == 1,
	      "CONTROL: the producer decoded exactly one movie and is stuck on the second");
	prefetcher.cancelAndJoin(); // must return, not hang
	check(prefetcher.stats().decoded == 1,
	      "cancelAndJoin returned without the producer sneaking another decode through");
}

void testCancelWhileProducerBlockedOnQueue()
{
	Watchdog dog(30.0, "cancel while the producer waits for a queue slot");
	// Capacity 2, budget for 8: the queue, not the budget, is what stops the
	// producer here.
	MoviePrefetcher prefetcher(movieNames(20), unitOptions(8, 2));
	FakeLoader loader;
	loader.install(prefetcher);
	prefetcher.start();
	// Let the producer fill the queue and block on it without consuming.
	std::this_thread::sleep_for(std::chrono::milliseconds(200));
	// `>= 1` would be satisfied by a single push and would NOT show the queue
	// was full, which is the state this case exists to cancel out of.
	check(prefetcher.stats().peak_queue_occupancy == 2,
	      "CONTROL: the queue reached its capacity, so the producer really is "
	      "blocked on a queue slot and not on the budget");
	check(prefetcher.budget().blockedSeconds() == 0.0,
	      "CONTROL: and it is not blocked on the budget instead");
	prefetcher.cancelAndJoin();
	check(prefetcher.budget().reservedBytes() == 0,
	      "cancellation drained the queue and returned every reservation");
}

void testCancelWhileConsumerWaits()
{
	Watchdog dog(30.0, "cancel while the consumer waits for data");
	MoviePrefetcher prefetcher(movieNames(4), unitOptions(3));
	FakeLoader loader;
	loader.decode_seconds = 5.0; // consumer will be waiting when we cancel
	loader.install(prefetcher);
	prefetcher.start();

	std::atomic<bool> returned{false}, got{true};
	std::thread consumer([&] {
		MoviePrefetchRecord record;
		got = prefetcher.next(record);
		returned = true;
	});
	std::this_thread::sleep_for(std::chrono::milliseconds(100));
	check(!returned.load(), "CONTROL: the consumer really was blocked on an empty queue");
	prefetcher.cancelAndJoin();
	consumer.join();
	check(returned.load(), "the blocked consumer was woken by cancellation");
	check(!got.load(), "and reported no record rather than an empty one");
}

void testDestructorJoinsWithoutDraining()
{
	Watchdog dog(30.0, "destroying a running prefetcher joins it");
	{
		MoviePrefetcher prefetcher(movieNames(50), unitOptions(4, 3));
		FakeLoader loader;
		loader.decode_seconds = 0.001;
		loader.install(prefetcher);
		prefetcher.start();
		MoviePrefetchRecord record;
		check(prefetcher.next(record), "consume one, then abandon the rest");
		std::this_thread::sleep_for(std::chrono::milliseconds(50));
		// Establish that there is something to join: the producer must still be
		// working through the remaining 49 movies, not already finished.
		check(prefetcher.stats().decoded < 50,
		      "CONTROL: the producer is genuinely mid-flight when it is destroyed");
		// Falls out of scope with the producer running, as an exception
		// unwinding out of the movie loop would leave it.
	}
	// Reaching here at all is the assertion: the watchdog fires otherwise, and
	// a non-joined producer would trip TSan or crash on the destroyed budget.
	check(true, "the destructor cancelled and joined without hanging");
}

void testMixedGeometryAccounting()
{
	Watchdog dog(30.0, "mixed geometries are each charged their own estimate");
	// Alternating geometries: the estimate must follow the movie, not a cached
	// first-movie size.
	std::vector<FileName> movies = movieNames(6);
	MoviePrefetcher prefetcher(movies, unitOptions(6));
	std::atomic<long> probe_count{0};
	prefetcher.setProbeForTesting([&](const FileName &fn) {
		const long i = probe_count++;
		MovieGeometry geometry;
		geometry.nx = (i % 2 == 0) ? kNx : kNx / 2;
		geometry.ny = kNy;
		geometry.nn = (i % 3 == 0) ? kNFrames : kNFrames / 2;
		return geometry;
	});
	prefetcher.setLoaderForTesting([](const FileName &, MoviePrefetchRecord &record, int) {
		record.Iframes.resize(record.frames.size());
	});
	prefetcher.start();

	for (int i = 0; i < 6; i++)
	{
		MoviePrefetchRecord record;
		check(prefetcher.next(record), "mixed-geometry record " + std::to_string(i));
		const size_t expected = movieio::estimateDecodedMovieBytes(
			record.geometry.nx, record.geometry.ny, (int)record.frames.size(), kIoThreads);
		check(record.reservation.bytes() == expected,
		      "movie " + std::to_string(i) + " is charged its own geometry");
		check((int)record.Iframes.size() == (int)record.frames.size(),
		      "the decoded frame count follows the geometry");
	}
	check(prefetcher.budget().reservedBytes() == 0, "nothing is left charged");
}

void testFrameSelection()
{
	check(movieio::selectFrames(5, 1, -1) == std::vector<int>({0, 1, 2, 3, 4}),
	      "the default selects every frame");
	check(movieio::selectFrames(5, 2, 4) == std::vector<int>({1, 2, 3}),
	      "first/last frame options are 1-indexed and inclusive");
	check(movieio::selectFrames(5, 6, -1).empty(),
	      "a first frame past the end selects nothing");
	check(movieio::selectFrames(0, 1, -1).empty(), "an empty movie selects nothing");
}

void testUnprobeableAutomaticBudget()
{
	// This covers ONLY the fallback branch of resolveBudgetBytes: no movie can
	// be probed, so the documented `queue_capacity + 2` units cannot be
	// computed. The real 3x-the-first-movie path needs actual files on disk and
	// is covered end to end by the Python `normal` case, which asserts the
	// budget equals three times an independently recomputed estimate.
	MoviePrefetcher::Options options;
	options.budget_bytes = 0;
	options.queue_capacity = 2;
	options.n_io_threads = kIoThreads;
	// resolveBudgetBytes probes real files, and these do not exist, so every
	// probe throws and the fallback limit applies. That path must not crash and
	// must still leave a usable prefetcher.
	std::cout << "  (the RelionError reports below are expected: this case probes"
	             " deliberately absent files)" << std::endl;
	MoviePrefetcher prefetcher(movieNames(2), options);
	check(prefetcher.budget().limitBytes() >= 1,
	      "an unprobeable list still yields a usable, nonzero budget");
	// Every movie must then take the in-line path rather than being admitted
	// against a meaningless budget.
	prefetcher.start();
	for (int i = 0; i < 2; i++)
	{
		MoviePrefetchRecord record;
		check(prefetcher.next(record), "a record still arrives for movie " + std::to_string(i));
		check(record.mode != MoviePrefetchRecord::Mode::Decoded,
		      "nothing is decoded against the fallback budget");
	}
}


// --- Codex review controls -------------------------------------------------

// Admission is a positive whitelist, not "everything except EER and compressed
// MRC". This is discriminating: under a negative check every one of the
// rejected extensions below is admitted to the producer, so the test fails.
void testFormatWhitelistIsPositive()
{
	struct Case { const char *name; bool prefetchable; };
	const Case cases[] = {
		// Admitted: the readers this change actually validated.
		{"movie.mrc",       true},
		{"movie.mrcs",      true},
		{"movie.tif",       true},
		{"movie.tiff",      true},
		{"movie.MRCS",      true},  // getFileFormat() lowercases
		{"movie.dat:mrcs",  true},  // explicit override picks the real reader
		// Rejected: other formats Image accepts. A negative check admits all of
		// these, which is the defect this case exists to catch.
		{"movie.spi",       false},
		{"movie.stk",       false},
		{"movie.xmp",       false},
		{"movie.vol",       false},
		{"movie.img",       false}, // IMAGIC pair
		{"movie.hed",       false},
		{"movie.st",        false}, // MRC-family, but not a validated route here
		{"movie.map",       false}, // 3D map, not a stack
		{"movie.dm4",       false},
		{"movie",           false}, // no extension: Image defaults to SPIDER
		{"movie.mrcs#512",  false}, // raw specifier
		// Rejected, and independently rejected by their own predicates.
		{"movie.eer",       false},
		{"movie.ecc",       false},
		{"movie.mrc.bz2",   false},
		{"movie.mrcs.xz",   false},
		{"movie.mrc.zst",   false},
	};
	for (const Case &c : cases)
	{
		check(movieio::isPrefetchableMovie(FileName(c.name)) == c.prefetchable,
		      std::string("format routing for ") + c.name + " should be " +
		      (c.prefetchable ? "prefetchable" : "in-line"));
	}
}

// The automatic budget is three movie estimates, full stop. Scaling it by the
// queue capacity would mean raising a count limit silently raises the memory
// ceiling, and a large enough queue would disable the default bound while the
// CLI still promises 3x. Discriminating: under the old
// `queue_capacity + 2` rule, capacities 2 and 64 give 4x and 66x.
void testAutomaticBudgetIgnoresQueueCapacity()
{
	Watchdog dog(30.0, "automatic budget is independent of queue capacity");
	// Real, probeable files: otherwise every capacity hits the unprobeable
	// fallback and the comparison below is between five identical constants.
	TempDir tmp;
	std::vector<FileName> fixtures;
	for (int i = 0; i < 2; i++)
	{
		const std::string path = tmp.file("auto" + std::to_string(i) + ".mrcs");
		writeTinyMrcStack(path, kNx, kNy, kNFrames);
		fixtures.push_back(FileName(path));
	}
	const size_t expected =
		movieio::saturatingMul(unitBytes(), 3); // three estimates, never more
	const size_t queue_capacities[] = {1, 2, 3, 8, 64};
	size_t first_limit = 0;
	for (size_t capacity : queue_capacities)
	{
		MoviePrefetcher::Options options;
		options.budget_bytes = 0; // automatic
		options.queue_capacity = capacity;
		options.n_io_threads = kIoThreads;
		options.first_frame_sum = 1;
		options.last_frame_sum = -1;
		const size_t resolved = MoviePrefetcher::resolveBudgetBytes(fixtures, options);
		if (capacity == queue_capacities[0]) first_limit = resolved;
		check(resolved == first_limit,
		      "queue capacity " + std::to_string(capacity) +
		      " must not change the automatic byte limit");
		// Absolute, not just self-consistent: under the old
		// `queue_capacity + 2` rule these would be 3x, 4x, 5x, 10x and 66x.
		check(resolved == expected,
		      "the automatic limit is exactly three estimates at queue capacity " +
		      std::to_string(capacity));
	}
	// CONTROL: the fixtures really were probeable, so the five equal answers
	// above are not five copies of the unprobeable fallback.
	check(first_limit == expected && first_limit > 1,
	      "CONTROL: the budget was computed from a real probe, not the fallback");
	// And an explicit budget is still honoured verbatim.
	MoviePrefetcher::Options explicit_options;
	explicit_options.budget_bytes = 123456;
	explicit_options.queue_capacity = 8;
	check(MoviePrefetcher::resolveBudgetBytes(fixtures, explicit_options) == 123456,
	      "an explicit budget is not rescaled by the queue capacity");
}

// A queue larger than the byte budget can hold must be stopped by the BYTES,
// not merely by the slot count, and must not overflow the bound while doing so.
void testQueueLargerThanBudgetIsStoppedByBytes()
{
	Watchdog dog(60.0, "an oversized queue is bounded by bytes, not slots");
	const int n = 10;
	MoviePrefetcher::Options options = unitOptions(3, 8); // 3 units, 8 slots
	MoviePrefetcher prefetcher(movieNames(n), options);
	FakeLoader loader;
	loader.decode_seconds = 0.002;
	loader.install(prefetcher);
	prefetcher.start();

	const size_t limit = prefetcher.budget().limitBytes();
	size_t observed_peak_occupancy = 0;
	for (int i = 0; i < n; i++)
	{
		MoviePrefetchRecord record;
		check(prefetcher.next(record), "record " + std::to_string(i) + " arrives");
		for (int sample = 0; sample < 20; sample++)
		{
			check(prefetcher.budget().reservedBytes() <= limit,
			      "an 8-slot queue never exceeds a 3-unit byte budget");
			const size_t occupancy = prefetcher.stats().peak_queue_occupancy;
			if (occupancy > observed_peak_occupancy) observed_peak_occupancy = occupancy;
			std::this_thread::sleep_for(std::chrono::microseconds(200));
		}
	}
	// Control: with 8 slots and a 3-unit budget the queue must be held BELOW
	// its capacity by the bytes. If it ever reached 8 the budget was not the
	// binding constraint and this case proved nothing.
	check(observed_peak_occupancy < 8,
	      "CONTROL: the byte budget, not the slot count, is what bounded the queue");
	check(prefetcher.budget().peakReservedBytes() <= limit,
	      "the recorded peak stayed within the budget");
}

// Reusing one record across repeated next() calls must free the old frames
// BEFORE their bytes are returned. Observed exactly, via the budget's release
// hook, which runs after the bytes are back and before any waiter is woken --
// so with a defaulted move assignment the old frames are still allocated at
// that instant and the count below is nonzero.
void testReusedRecordFreesFramesBeforeReturningBytes()
{
	Watchdog dog(30.0, "reused record frees frames before returning bytes");
	ByteBudget budget(unitBytes() * 4);

	MoviePrefetchRecord reused;
	size_t frames_live_at_release = 0;
	long releases = 0;
	budget.setReleaseObserverForTesting([&](size_t, size_t) {
		releases++;
		if (!reused.Iframes.empty()) frames_live_at_release += reused.Iframes.size();
	});

	for (int round = 0; round < 3; round++)
	{
		MoviePrefetchRecord fresh;
		fresh.index = round;
		fresh.reservation = budget.reserve(unitBytes());
		check(fresh.reservation.held(), "round " + std::to_string(round) + " reserved");
		fresh.Iframes.resize(kNFrames);
		// Move-assign onto a record that already owns frames and a reservation.
		reused = std::move(fresh);
		check(reused.index == round, "the reused record took the new contents");
		check((int)reused.Iframes.size() == kNFrames, "and the new frames");
		check(budget.reservedBytes() == unitBytes(),
		      "exactly one movie is charged after the handover");
	}
	check(releases >= 2, "CONTROL: the move assignment really did release old reservations");
	check(frames_live_at_release == 0,
	      "the previous frames were freed before their bytes were returned");

	// Self-move must not free anything or return bytes.
	reused = std::move(reused);
	check(reused.reservation.held(), "self-move keeps the reservation");
	check((int)reused.Iframes.size() == kNFrames, "self-move keeps the frames");
	check(budget.reservedBytes() == unitBytes(), "self-move returns nothing");

	budget.setReleaseObserverForTesting(nullptr);
	reused = MoviePrefetchRecord();
	check(budget.reservedBytes() == 0, "the last handover returned the bytes");
}

// The same property through the real producer/consumer, with the consumer
// reusing one record as next()'s signature invites.
void testReusedRecordAcrossRealHandovers()
{
	Watchdog dog(30.0, "reused record across real next() handovers");
	const int n = 8;
	MoviePrefetcher prefetcher(movieNames(n), unitOptions(2));
	FakeLoader loader;
	loader.install(prefetcher);
	prefetcher.start();

	MoviePrefetchRecord record; // ONE record, reused
	int received = 0;
	while (prefetcher.next(record))
	{
		check(record.index == received, "records still arrive in order when reused");
		check(record.mode == MoviePrefetchRecord::Mode::Decoded, "and are decoded");
		check(prefetcher.budget().reservedBytes() <= prefetcher.budget().limitBytes(),
		      "the bound holds across a reused record");
		received++;
	}
	check(received == n, "every movie arrived through the reused record");
	check(prefetcher.budget().peakReservedBytes() <= prefetcher.budget().limitBytes(),
	      "the recorded peak never exceeded the budget");
	record = MoviePrefetchRecord();
	check(prefetcher.budget().reservedBytes() == 0, "nothing is left charged");
}
} // namespace

int main()
{
	testSizeArithmetic();
	testFrameSelection();
	testBudgetBasics();
	testBudgetBlocksAndWakes();
	testBudgetCancelWakesWaiter();
	testForcedGrant();
	testRecordFreesFramesBeforeReturningBytes();
	testDegenerateGeometryIsNotFree();
	testBoundedQueue();
	testOrderingAndCompletion();
	testAccountingBound();
	testBlockedBudgetStillCompletes();
	testOversizedMovieFallsBackInline();
	testUnsupportedFormatFallsBackInline();
	testProducerErrorIsMovieTagged();
	testCancelWhileProducerBlockedOnBudget();
	testCancelWhileProducerBlockedOnQueue();
	testCancelWhileConsumerWaits();
	testDestructorJoinsWithoutDraining();
	testMixedGeometryAccounting();
	testUnprobeableAutomaticBudget();
	testFormatWhitelistIsPositive();
	testAutomaticBudgetIgnoresQueueCapacity();
	testQueueLargerThanBudgetIsStoppedByBytes();
	testReusedRecordFreesFramesBeforeReturningBytes();
	testReusedRecordAcrossRealHandovers();

	if (failures != 0)
	{
		std::cerr << failures << " prefetch lifecycle check(s) failed" << std::endl;
		return 1;
	}
	std::cout << "prefetch lifecycle: all checks passed" << std::endl;
	return 0;
}
