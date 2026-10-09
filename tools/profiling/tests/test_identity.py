"""lib/identity.py: what must match, what is normalised, what is excluded."""
import os
import shutil
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import identity  # noqa: E402


def write_tree(root, stamp="01-Jan-26  00:00:00", payload=b"\x01\x02" * 32, star_extra="", nsymbt=0):
    os.makedirs(os.path.join(root, "Movies"), exist_ok=True)
    hdr = bytearray(1024)
    struct.pack_into("<3i", hdr, 0, 4, 4, 1)
    struct.pack_into("<i", hdr, 92, nsymbt)
    hdr[224:224 + len(stamp)] = stamp.encode()
    with open(os.path.join(root, "Movies", "m1.mrc"), "wb") as f:
        f.write(bytes(hdr) + b"E" * nsymbt + payload)
    with open(os.path.join(root, "Movies", "m1.star"), "w") as f:
        f.write("data_\n# output %s/Movies/m1.mrc\n%s" % (root, star_extra))
    with open(os.path.join(root, "Movies", "m1_shifts.eps"), "w") as f:
        f.write("%%Title: " + root + "/Movies/m1_shifts.eps\n")
    with open(os.path.join(root, "Movies", "m1.log"), "w") as f:
        f.write("Full movie wall time: %s s\n" % stamp)
    with open(os.path.join(root, "logfile.pdf"), "w") as f:
        f.write(stamp)


class Identity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.a, self.b = os.path.join(self.tmp, "runA", "out"), os.path.join(self.tmp, "runB", "out")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_identical_apart_from_labels_logs_pdf_and_root(self):
        write_tree(self.a, stamp="01-Jan-26  00:00:00")
        write_tree(self.b, stamp="02-Feb-26  11:11:11")
        r = identity.compare_trees(self.a, self.b, expect_mrc=1)
        self.assertTrue(r["identical"], r)
        self.assertEqual(r["mrc_compared"], 1)
        self.assertEqual(sorted(x["file"] for x in r["excluded"]), ["Movies/m1.log", "logfile.pdf"])

    def test_payload_difference(self):
        write_tree(self.a)
        write_tree(self.b, payload=b"\x01\x02" * 31 + b"\x01\x03")
        r = identity.compare_trees(self.a, self.b)
        self.assertFalse(r["identical"])
        self.assertEqual(r["differences"][0]["difference"], "payload differs at byte %d" % (1024 + 63))

    def test_core_header_difference(self):
        write_tree(self.a)
        write_tree(self.b)
        p = os.path.join(self.b, "Movies", "m1.mrc")
        data = bytearray(open(p, "rb").read())
        data[76] ^= 1   # amin
        open(p, "wb").write(bytes(data))
        r = identity.compare_trees(self.a, self.b)
        self.assertEqual(r["differences"][0]["difference"], "core header differs at byte 76")

    def test_extended_header_difference(self):
        write_tree(self.a, nsymbt=8)
        write_tree(self.b, nsymbt=8)
        p = os.path.join(self.b, "Movies", "m1.mrc")
        data = bytearray(open(p, "rb").read())
        data[1027] = ord("F")
        open(p, "wb").write(bytes(data))
        self.assertEqual(identity.compare_trees(self.a, self.b)["differences"][0]["difference"],
                         "extended header differs")

    def test_star_difference_beyond_root(self):
        write_tree(self.a)
        write_tree(self.b, star_extra="_rlnAccumMotionTotal 1.5\n")
        r = identity.compare_trees(self.a, self.b)
        self.assertEqual([d["file"] for d in r["differences"]], ["Movies/m1.star"])

    def test_inventory_difference(self):
        write_tree(self.a)
        write_tree(self.b)
        os.remove(os.path.join(self.b, "Movies", "m1_shifts.eps"))
        r = identity.compare_trees(self.a, self.b)
        self.assertFalse(r["identical"])
        self.assertEqual(r["only_a"], ["Movies/m1_shifts.eps"])

    def test_empty_trees_fail(self):
        os.makedirs(self.a)
        os.makedirs(self.b)
        r = identity.compare_trees(self.a, self.b)
        self.assertFalse(r["identical"])
        self.assertIn("no MRC products compared", r["problems"])

    def test_expected_count(self):
        write_tree(self.a)
        write_tree(self.b)
        self.assertFalse(identity.compare_trees(self.a, self.b, expect_mrc=2)["identical"])


if __name__ == "__main__":
    unittest.main()
