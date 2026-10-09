// StageProfile must ignore stage markers from non-owner threads without
// touching owner-only state (#154 review, P2). OpenMP workers inside CPU
// alignPatch reach the same RCTIC/RCTOC markers as the main thread.
//
// The owner runs push/pop pairs while worker threads call push/pop on the same
// instance. Correct code: workers return before reading any owner-only state,
// so (1) the owner's nested stack balances exactly and only owner sub-stages
// are recorded, and (2) under -fsanitize=thread there is no race report.
// The pre-fix code read nested.empty() before the owner check; ThreadSanitizer
// reports that as a data race (the TSan build of this test fails on it).
#include "src/stage_profile.h"

#include <atomic>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
#include <thread>
#include <vector>
#include <unistd.h>

int main()
{
	char path[] = "/tmp/mc_stage_profile_threadsXXXXXX";
	const int fd = mkstemp(path);
	if (fd < 0) { std::perror("mkstemp"); return 1; }
	close(fd);
	unlink(path);  // enable() creates it exclusively
	StageProfile &p = StageProfile::instance();
	p.enable(path);
	// Path swap after the exclusive create (#162 review, P1): another process
	// replaces the profile path with a symlink to a victim. Writes must keep
	// going to the inode that enable() created; the victim must be untouched.
	char victim[] = "/tmp/mc_stage_profile_victimXXXXXX";
	const int vfd = mkstemp(victim);
	if (vfd < 0) { std::perror("mkstemp victim"); return 1; }
	const char original[] = "victim input bytes\n";
	if (write(vfd, original, sizeof original - 1) != (ssize_t)(sizeof original - 1)) return 1;
	close(vfd);
	std::string moved = std::string(path) + ".moved";
	if (rename(path, moved.c_str()) != 0 || symlink(victim, path) != 0) { std::perror("swap"); return 1; }
	p.beginRun();
	p.beginMovie(0, "threads");
	p.next("work");

	std::atomic<bool> go{false}, stop{false};
	std::atomic<long> worker_calls{0};
	std::vector<std::thread> workers;
	for (int t = 0; t < 3; t++)
		workers.emplace_back([&] {
			while (!go.load()) {}
			while (!stop.load()) {
				p.push("WORKER");
				p.pop();
				worker_calls++;
			}
		});
	go = true;
	const int n = 20000;
	for (int i = 0; i < n; i++) {
		p.push("OWNER");
		p.pop();
	}
	stop = true;
	for (auto &w : workers) w.join();
	p.endMovie(true);
	p.endRun(1);

	std::ifstream vin(victim);
	std::string victim_now((std::istreambuf_iterator<char>(vin)), std::istreambuf_iterator<char>());
	unlink(victim);
	unlink(path);   // the symlink
	std::ifstream in(moved);
	std::string movie, line;
	while (std::getline(in, line))
		if (line.find("\"type\":\"movie\"") != std::string::npos) movie = line;
	unlink(moved.c_str());
	int failures = 0;
	auto check = [&](bool ok, const char *what) {
		std::printf("%s %s\n", ok ? "ok  " : "FAIL", what);
		if (!ok) failures++;
	};
	check(victim_now == original, "a path swapped to a symlink after enable() is not written through");
	check(!movie.empty(), "the profile went to the inode enable() created");
	check(worker_calls.load() > 0, "workers ran concurrently with the owner");
	check(movie.find("\"name\":\"work/OWNER\",\"n\":20000") != std::string::npos,
	      "owner sub-stage recorded exactly n times");
	check(movie.find("WORKER") == std::string::npos, "worker markers ignored");
	check(!p.writeFailed(), "profile written without error");
	return failures ? 1 : 0;
}
