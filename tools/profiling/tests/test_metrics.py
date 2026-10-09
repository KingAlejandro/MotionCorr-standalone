"""Known-answer tests for lib/metrics.py and the Nsight query layer.

The fixture (fixture_db.py) is a SQLite file on the real nsys 2024.6.2 export
schema with hand-computed answers. A broken union, a gap charged to the stage
where it starts instead of being split, or a miscounted call fails here.
"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fixture_db  # noqa: E402
from lib import metrics, nsys_db  # noqa: E402

E = fixture_db.EXPECTED


class Intervals(unittest.TestCase):
    def test_union_counts_overlap_once(self):
        self.assertEqual(metrics.union([(150, 250), (220, 300), (280, 400), (700, 800)]), [(150, 400), (700, 800)])
        self.assertEqual(metrics.total(metrics.union([(0, 10), (5, 15), (15, 20)])), 20)
        self.assertEqual(metrics.union([(5, 6), (0, 10)]), [(0, 10)])

    def test_clip_and_complement(self):
        m = [(150, 400), (700, 850)]
        self.assertEqual(metrics.clip(m, 200, 600), 200)
        self.assertEqual(metrics.clip(m, 600, 1000), 150)
        self.assertEqual(metrics.clip(m, 0, 100), 0)
        self.assertEqual(metrics.complement(m, 600, 1000), [(600, 700), (850, 1000)])
        self.assertEqual(metrics.complement(m, 160, 390), [])
        self.assertEqual(metrics.complement([], 0, 5), [(0, 5)])

    def test_rejects_reversed_interval(self):
        with self.assertRaises(metrics.MetricError):
            metrics.union([(10, 5)])


class FixtureCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = fixture_db.build(os.path.join(cls.tmp.name, "fixture.sqlite"))
        cls.db = nsys_db.NsysDB(cls.path)
        cls.a = metrics.analyze(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.tmp.cleanup()

    def seg(self, key):
        return [row[key] for row in self.a["per_segment"]]


class KnownAnswers(FixtureCase):
    def test_window_and_segments(self):
        self.assertEqual(tuple(self.a["window_ns"]), E["window"])
        got = [(s["label"], s["start"], s["end"]) for s in self.a["segments"]]
        self.assertEqual(got, E["segments"])
        # The segments tile the window exactly.
        self.assertEqual(sum(e - s for _, s, e in got), E["window"][1] - E["window"][0])

    def test_union_busy_time(self):
        self.assertEqual(self.seg("busy_ns"), E["busy"])
        self.assertEqual(self.seg("kernel_busy_ns"), E["kernel_busy"])
        self.assertEqual(self.seg("copy_busy_ns"), E["copy_busy"])
        for k, v in E["totals"].items():
            self.assertEqual(self.a["totals"][k], v, k)

    def test_idle_split_at_stage_boundaries(self):
        self.assertEqual(self.seg("idle_ns"), E["idle"])
        self.assertEqual(self.seg("idle_intervals"), E["idle_intervals"])
        segs = [metrics.Segment(s["start"], s["end"], s["label"], s["movie"], s["kind"]) for s in self.a["segments"]]
        busy = metrics.union([(150, 250), (220, 300), (700, 800), (1300, 1350), (280, 400), (790, 850)])
        self.assertEqual([r["max_idle_interval_ns"] for r in metrics.device_per_segment(segs, busy)],
                         E["max_idle_interval"])
        self.assertEqual(sum(self.seg("idle_ns")), E["totals"]["idle_ns"])

    def test_sync_census_and_allocations(self):
        self.assertEqual(self.seg("sync_calls"), E["sync_calls"])
        self.assertEqual(self.seg("sync_blocked_idle_ns"), E["sync_blocked_idle"])
        self.assertEqual(self.seg("malloc"), E["malloc"])
        self.assertEqual(self.seg("free"), E["free"])
        b = self.a["syncs_by_stage"]["B"]
        self.assertEqual(b["device sync"], {"n": 1, "host_ns": 170, "device_busy_ns": 120, "blocked_idle_ns": 50})
        self.assertEqual(b["free (implicit sync)"]["n"], 1)
        self.assertEqual(self.a["syncs_by_stage"]["A"]["synchronous memcpy"]["blocked_idle_ns"], 10)
        self.assertEqual(self.a["apis"]["cudaLaunchKernel"]["n"], 3)

    def test_kernel_launches_and_copies(self):
        self.assertEqual(self.seg("kernels"), E["kernels"])
        self.assertEqual(self.a["copies_by_stage"]["A"], {"Host-to-Device Pageable->Device":
                                                          {"n": 1, "bytes": 1000, "device_ns": 120}})
        self.assertEqual(self.a["copies_by_stage"]["B"]["Device-to-Host Device->Pinned"]["bytes"], 500)
        self.assertEqual(self.seg("pageable_copies"), [0, 0, 1, 0, 0, 0, 0, 0, 0])
        top = self.a["top_kernels"]
        self.assertEqual([(k["name"], k["launches"], k["device_ns"]) for k in top],
                         [("k_alpha", 2, 200), ("k_beta", 2, 130)])

    def test_memory_high_water(self):
        m = self.a["memory"]
        self.assertEqual(m["devices"]["0"]["peak_bytes"], E["mem_peak"])
        self.assertEqual(m["devices"]["0"]["peak_time_ns"], E["mem_peak_time"])
        self.assertEqual(m["devices"]["0"]["peak_segment"], "A")
        self.assertEqual(m["devices"]["0"]["peak_movie"], 1)
        self.assertEqual(m["devices"]["0"]["residual_bytes"], E["mem_residual"])
        self.assertEqual(m["segment_peak_bytes"], E["segment_mem_peak"])
        self.assertEqual(m["duplicate_device_static_counted_once"], 1)
        self.assertEqual(m["allocations_by_kind"], {"Device": 3, "Device Static": 1})
        self.assertEqual(m["frees"], 3)

    def test_stage_aggregation(self):
        a = self.a["stages"]["A"]
        self.assertEqual(a["wall_ns"]["per_movie"], [400, 300])
        self.assertEqual(a["busy_ns"]["per_movie"], [200, 50])
        self.assertEqual(a["idle_ns"]["per_movie"], [200, 250])
        self.assertEqual(a["wall_ns"]["first"], 400)
        self.assertEqual(a["wall_ns"]["steady_median"], 300)
        self.assertEqual(a["mem_peak_bytes"], 258)
        self.assertEqual(self.a["stages"]["setup"]["mem_peak_bytes"], 58)
        self.assertEqual(self.a["stages"]["between movies"]["wall_ns"]["sum"], 100)
        self.assertNotIn("SUB", self.a["stages"])      # nested sub-stage is not a top-level segment
        self.assertNotIn("worker", self.a["stages"])   # other thread's range is not a movie

    def test_timeline(self):
        tl = metrics.timeline(self.db, self.a)
        self.assertEqual(len(tl["movies"]), 2)
        m0 = tl["movies"][0]
        self.assertEqual([st[0] for st in m0["stages"]], ["setup", "A", "B"])
        self.assertEqual(len(m0["kernels"]), 3)
        self.assertEqual(len(tl["movies"][1]["kernels"]), 1)


class Robustness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_optional_tables_absent(self):
        p = fixture_db.build(os.path.join(self.tmp.name, "f.sqlite"),
                             drop_tables=("CUPTI_ACTIVITY_KIND_MEMSET", "CUDA_GPU_MEMORY_USAGE_EVENTS",
                                          "CUPTI_ACTIVITY_KIND_SYNCHRONIZATION"))
        db = nsys_db.NsysDB(p)
        a = metrics.analyze(db)
        self.assertIsNone(a["memory"])
        self.assertEqual(a["totals"]["busy_ns"], E["totals"]["busy_ns"])

    def test_missing_required_column_is_named(self):
        def alter(con, _):
            con.execute("alter table CUPTI_ACTIVITY_KIND_MEMCPY rename column copyKind to kindOfCopy")
        p = fixture_db.build(os.path.join(self.tmp.name, "f.sqlite"), extra=alter)
        with self.assertRaisesRegex(nsys_db.SchemaError, "CUPTI_ACTIVITY_KIND_MEMCPY lacks column.*copyKind"):
            metrics.analyze(nsys_db.NsysDB(p))

    def test_no_nvtx_gives_whole_trace(self):
        p = fixture_db.build(os.path.join(self.tmp.name, "f.sqlite"), drop_nvtx=True)
        a = metrics.analyze(nsys_db.NsysDB(p))
        self.assertEqual([s["label"] for s in a["segments"]], [metrics.NO_STAGES])
        self.assertEqual(a["per_segment"][0]["busy_ns"], 450)

    def test_unmatched_free_is_an_error(self):
        def bad(con, ins):
            ins(con, "CUDA_GPU_MEMORY_USAGE_EVENTS", start=1950, globalPid=7, deviceId=0, contextId=1,
                address=0x77, bytes=4, memKind=2, memoryOperationType=1)
        p = fixture_db.build(os.path.join(self.tmp.name, "f.sqlite"), extra=bad)
        with self.assertRaisesRegex(metrics.MetricError, "unmatched"):
            metrics.analyze(nsys_db.NsysDB(p))

    def test_crossing_nvtx_ranges_rejected(self):
        with self.assertRaises(metrics.MetricError):
            metrics.nest([(0, 10, "movie", 1), (5, 15, "x", 1)])

    def test_not_sqlite(self):
        p = os.path.join(self.tmp.name, "x.sqlite")
        with open(p, "w") as f:
            f.write("not a database" * 100)
        with self.assertRaises(nsys_db.SchemaError):
            nsys_db.NsysDB(p).window()

    def test_schema_fixture_is_the_captured_one(self):
        con = sqlite3.connect(":memory:")
        con.executescript(open(fixture_db.SCHEMA).read())
        meta = dict(con.execute("select name, value from META_DATA_EXPORT"))
        self.assertEqual(meta["EXPORT_PRODUCT_VERSION"], "2024.6.2.225")


class Folded(FixtureCase):
    def test_folded_stacks(self):
        samples, frames, names = self.db.sampling()
        folded, dropped = metrics.folded_stacks(samples, frames, names)
        self.assertEqual(folded, {"motioncorr;main;do_work;[k] page_fault": 1, "motioncorr;main;[libfoo.so]": 1})
        self.assertEqual(dropped, 1)


class NcuSummary(unittest.TestCase):
    CSV = "\n".join([
        "==PROF== Connected to process 1",
        '"ID","Process ID","Process Name","Host Name","Kernel Name","Context","Stream","Block Size","Grid Size",'
        '"Device","CC","Section Name","Metric Name","Metric Unit","Metric Value"',
        '"0","1","motioncorr","h","k_a(float*)","1","7","(128, 1, 1)","(4, 1, 1)","0","8.0","GPU Speed Of Light Throughput","Memory Throughput","%","80.5"',
        '"0","1","motioncorr","h","k_a(float*)","1","7","(128, 1, 1)","(4, 1, 1)","0","8.0","GPU Speed Of Light Throughput","Memory Throughput","Gbyte/s","1,200.00"',
        '"0","1","motioncorr","h","k_a(float*)","1","7","(128, 1, 1)","(4, 1, 1)","0","8.0","GPU Speed Of Light Throughput","Duration","ns","2,000"',
        '"1","1","motioncorr","h","k_a(float*)","1","7","(128, 1, 1)","(4, 1, 1)","0","8.0","GPU Speed Of Light Throughput","Memory Throughput","%","90.5"',
        '"1","1","motioncorr","h","k_a(float*)","1","7","(128, 1, 1)","(4, 1, 1)","0","8.0","Occupancy","Achieved Occupancy","%","50"',
    ])

    def test_unit_filter(self):
        s = metrics.ncu_summary(self.CSV)
        k = s["kernels"]["k_a"]
        self.assertEqual(k["mem_pct"], 85.5)            # the Gbyte/s row is not averaged in
        self.assertEqual(k["ncu_duration_us"], 2.0)
        self.assertEqual(k["launches_profiled"], 2)
        self.assertEqual(s["units_rejected"], {"Memory Throughput": ["Gbyte/s"]})

    def test_no_header(self):
        with self.assertRaises(metrics.MetricError):
            metrics.ncu_summary("==WARNING== No kernels were profiled.\n")


if __name__ == "__main__":
    unittest.main()
