// Lifecycle and admission tests for the bounded next-movie prefetch (issue #94).
//
// These are the cheap checks that gate the prototype: every one of them runs in
// well under a second, touches no filesystem and needs no GPU. They exist
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
		check(budget.forcedGrants() == 1, "the override is counted");
		check(budget.peakReservedBytes() >= 4000, "the peak shows the override");
	}
	check(budget.reservedBytes() == 0, "a forced grant is returned like any other");
}

void testBoundedQueue()
{
	Watchdog dog(10.0, "bounded queue push/pop/finish/cancel");
	{
		BoundedQueue<int> queue(2);
		int out = -1;
		check(queue.push(1) && queue.push(2), "pushes up to capacity succeed");
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
	check(prefetcher.budget().forcedGrants() == 0, "no override was needed");
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

	// The consumer's own in-line load is charged through a counted forced grant.
	{
		ByteBudget::Reservation forced = prefetcher.reserveInline(unitBytes() * 10);
		check(forced.held(), "the consumer's in-line load is granted");
		check(prefetcher.budget().reservedBytes() > prefetcher.budget().limitBytes(),
		      "and is visible as an over-budget grant rather than untracked");
	}
	check(prefetcher.stats().forced_grants == 1, "the override is reported");
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
	std::this_thread::sleep_for(std::chrono::milliseconds(50));
	// The producer cannot reserve anything while `held` is alive.
	prefetcher.cancelAndJoin(); // must return, not hang
	check(true, "cancelAndJoin returned with the producer blocked on the budget");
}

void testCancelWhileProducerBlockedOnQueue()
{
	Watchdog dog(30.0, "cancel while the producer waits for a queue slot");
	MoviePrefetcher prefetcher(movieNames(20), unitOptions(8, 2));
	FakeLoader loader;
	loader.install(prefetcher);
	prefetcher.start();
	// Let the producer fill the queue and block on it without consuming.
	std::this_thread::sleep_for(std::chrono::milliseconds(100));
	check(prefetcher.stats().peak_queue_occupancy >= 1,
	      "CONTROL: the producer really did get ahead and fill the queue");
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
		// Falls out of scope with the producer mid-flight, as an exception
		// unwinding out of the movie loop would.
	}
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

void testAutomaticBudget()
{
	// With no explicit budget the limit is queue_capacity + 2 units, i.e.
	// producer-current + queued + consumer-active.
	MoviePrefetcher::Options options;
	options.budget_bytes = 0;
	options.queue_capacity = 2;
	options.n_io_threads = kIoThreads;
	// resolveBudgetBytes probes real files, and these do not exist, so every
	// probe throws and the fallback limit applies. That path must not crash and
	// must still leave a usable prefetcher.
	std::cout << "  (the two RelionError reports below are expected: this case probes"
	             " deliberately absent files)" << std::endl;
	MoviePrefetcher prefetcher(movieNames(2), options);
	check(prefetcher.budget().limitBytes() >= 1,
	      "an unprobeable list still yields a usable, nonzero budget");
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
	testAutomaticBudget();

	if (failures != 0)
	{
		std::cerr << failures << " prefetch lifecycle check(s) failed" << std::endl;
		return 1;
	}
	std::cout << "prefetch lifecycle: all checks passed" << std::endl;
	return 0;
}
