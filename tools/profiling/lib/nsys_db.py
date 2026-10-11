"""One query layer over an Nsight Systems SQLite export.

Schema reference: nsys 2024.6.2 export schema 3.16.1, captured from a real
export on 4GPUs (tests/fixtures/nsys_2024_6_schema.sql). Enum ids are always
resolved through the ENUM_* tables in the file, never hardcoded. A missing
optional table is an empty result; a missing required table or column raises
SchemaError naming it.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Sequence, Tuple


class SchemaError(Exception):
    pass


class NsysDB:
    def __init__(self, path: str):
        self.path = path
        try:
            self.con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
            self.tables = {r[0] for r in self.con.execute("select name from sqlite_master where type='table'")}
        except sqlite3.DatabaseError as e:
            raise SchemaError("%s: not an Nsight SQLite export: %s" % (path, e))
        self._strings: Optional[Dict[int, str]] = None
        self._cols: Dict[str, List[str]] = {}

    def close(self) -> None:
        self.con.close()

    # ------------------------------------------------------------- schema
    def has(self, table: str) -> bool:
        return table in self.tables

    def columns(self, table: str) -> List[str]:
        if table not in self._cols:
            self._cols[table] = [r[1] for r in self.con.execute("pragma table_info([%s])" % table)]
        return self._cols[table]

    def require(self, table: str, cols: Sequence[str]) -> None:
        if not self.has(table):
            raise SchemaError("%s: required table %s is missing" % (self.path, table))
        missing = [c for c in cols if c not in self.columns(table)]
        if missing:
            raise SchemaError("%s: table %s lacks column(s) %s" % (self.path, table, ", ".join(missing)))

    def _optional(self, table: str, cols: Sequence[str]) -> bool:
        if not self.has(table):
            return False
        self.require(table, cols)
        return True

    def meta(self) -> Dict[str, str]:
        if not self.has("META_DATA_EXPORT"):
            return {}
        return {k: v for k, v in self.con.execute("select name, value from META_DATA_EXPORT")}

    def strings(self) -> Dict[int, str]:
        if self._strings is None:
            self.require("StringIds", ["id", "value"])
            self._strings = {i: v for i, v in self.con.execute("select id, value from StringIds")}
        return self._strings

    def enum(self, table: str) -> Dict[int, str]:
        self.require(table, ["id"])
        col = "label" if "label" in self.columns(table) else "name"
        return {i: v for i, v in self.con.execute("select id, [%s] from [%s]" % (col, table))}

    # ------------------------------------------------------------- window
    def window(self) -> Tuple[int, int]:
        """First to last recorded activity of any traced kind."""
        lo, hi = None, None
        for t, s, e in (("CUPTI_ACTIVITY_KIND_KERNEL", "start", "end"),
                        ("CUPTI_ACTIVITY_KIND_MEMCPY", "start", "end"),
                        ("CUPTI_ACTIVITY_KIND_MEMSET", "start", "end"),
                        ("CUPTI_ACTIVITY_KIND_RUNTIME", "start", "end"),
                        ("NVTX_EVENTS", "start", "end"),
                        ("OSRT_API", "start", "end")):
            if not self.has(t):
                continue
            a, b = self.con.execute("select min(%s), max(%s) from [%s]" % (s, e, t)).fetchone()
            if a is None:
                continue
            lo = a if lo is None else min(lo, a)
            hi = b if hi is None else max(hi, b if b is not None else a)
        if lo is None:
            raise SchemaError("%s: no traced activity" % self.path)
        return lo, hi

    # ------------------------------------------------------------- device activity
    def kernels(self) -> List[Dict]:
        t = "CUPTI_ACTIVITY_KIND_KERNEL"
        cols = ["start", "end", "shortName", "demangledName", "streamId", "deviceId",
                "gridX", "gridY", "gridZ", "blockX", "blockY", "blockZ", "registersPerThread"]
        if not self._optional(t, cols):
            return []
        S = self.strings()
        out = []
        for r in self.con.execute("select %s from [%s] order by start" % (", ".join(cols), t)):
            out.append({"start": r[0], "end": r[1], "name": S.get(r[2], str(r[2])),
                        "demangled": S.get(r[3], str(r[3])), "stream": r[4], "device": r[5],
                        "grid": r[6] * r[7] * r[8], "block": r[9] * r[10] * r[11], "registers": r[12]})
        return out

    def memcpys(self) -> List[Dict]:
        t = "CUPTI_ACTIVITY_KIND_MEMCPY"
        if not self._optional(t, ["start", "end", "bytes", "copyKind", "srcKind", "dstKind", "streamId"]):
            return []
        oper = self.enum("ENUM_CUDA_MEMCPY_OPER")
        kind = self.enum("ENUM_CUDA_MEM_KIND")
        return [{"start": r[0], "end": r[1], "bytes": r[2], "direction": oper.get(r[3], "kind%s" % r[3]),
                 "src": kind.get(r[4], "kind%s" % r[4]), "dst": kind.get(r[5], "kind%s" % r[5]), "stream": r[6]}
                for r in self.con.execute("select start, end, bytes, copyKind, srcKind, dstKind, streamId "
                                          "from [%s] order by start" % t)]

    def memsets(self) -> List[Dict]:
        t = "CUPTI_ACTIVITY_KIND_MEMSET"
        if not self._optional(t, ["start", "end", "bytes"]):
            return []
        return [{"start": r[0], "end": r[1], "bytes": r[2]}
                for r in self.con.execute("select start, end, bytes from [%s] order by start" % t)]

    def runtime(self) -> List[Tuple[int, int, str, int]]:
        """CUDA runtime and driver API calls: (start, end, name, globalTid)."""
        t = "CUPTI_ACTIVITY_KIND_RUNTIME"
        if not self._optional(t, ["start", "end", "nameId", "globalTid"]):
            return []
        S = self.strings()
        return [(r[0], r[1], S.get(r[2], str(r[2])), r[3])
                for r in self.con.execute("select start, end, nameId, globalTid from [%s] order by start" % t)]

    def sync_records(self) -> Dict[str, int]:
        t = "CUPTI_ACTIVITY_KIND_SYNCHRONIZATION"
        if not self._optional(t, ["syncType"]):
            return {}
        st = self.enum("ENUM_CUPTI_SYNC_TYPE")
        return {st.get(k, str(k)): n for k, n in
                self.con.execute("select syncType, count(*) from [%s] group by syncType" % t)}

    def nvtx_ranges(self) -> List[Tuple[int, int, str, int]]:
        """Closed push/pop ranges: (start, end, text, globalTid)."""
        t = "NVTX_EVENTS"
        if not self._optional(t, ["start", "end", "eventType", "text", "textId", "globalTid"]):
            return []
        types = self.enum("ENUM_NSYS_EVENT_TYPE") if self.has("ENUM_NSYS_EVENT_TYPE") else {}
        pushpop = [i for i, v in types.items() if v == "NvtxPushPopRange"]
        if types and not pushpop:
            raise SchemaError("%s: ENUM_NSYS_EVENT_TYPE has no NvtxPushPopRange" % self.path)
        S = self.strings()
        where = "end is not null"
        if pushpop:
            where += " and eventType in (%s)" % ",".join(str(i) for i in pushpop)
        return [(r[0], r[1], r[2] if r[2] is not None else S.get(r[3], "?"), r[4])
                for r in self.con.execute("select start, end, text, textId, globalTid from [%s] where %s "
                                          "order by start" % (t, where))]

    def memory_events(self) -> List[Dict]:
        t = "CUDA_GPU_MEMORY_USAGE_EVENTS"
        if not self._optional(t, ["start", "globalPid", "contextId", "deviceId", "address", "bytes",
                                  "memKind", "memoryOperationType"]):
            return []
        ops = self.enum("ENUM_CUDA_DEV_MEM_EVENT_OPER")
        if sorted(ops.values()) != ["Allocation", "Deallocation"]:
            raise SchemaError("%s: unexpected memory operation enum %r" % (self.path, ops))
        kind = self.enum("ENUM_CUDA_MEM_KIND")
        return [{"start": r[0], "pid": r[1], "context": r[2], "device": r[3], "address": r[4],
                 "bytes": r[5], "kind": kind.get(r[6], str(r[6])), "op": ops[r[7]]}
                for r in self.con.execute("select start, globalPid, contextId, deviceId, address, bytes, "
                                          "memKind, memoryOperationType from [%s] order by start" % t)]

    # ------------------------------------------------------------- target
    def gpus(self) -> List[Dict]:
        if not self.has("TARGET_INFO_GPU"):
            return []
        want = [c for c in ("id", "name", "uuid", "busLocation", "smCount", "totalMemory", "clockRate")
                if c in self.columns("TARGET_INFO_GPU")]
        return [dict(zip(want, r)) for r in self.con.execute("select %s from TARGET_INFO_GPU" % ", ".join(want))]

    def system_env(self) -> Dict[str, str]:
        if not self.has("TARGET_INFO_SYSTEM_ENV"):
            return {}
        return {k: v for k, v in self.con.execute("select name, value from TARGET_INFO_SYSTEM_ENV")}

    # ------------------------------------------------------------- CPU sampling
    def has_sampling(self) -> bool:
        return self.has("COMPOSITE_EVENTS") and self.has("SAMPLING_CALLCHAINS") and \
            self.con.execute("select count(*) from COMPOSITE_EVENTS").fetchone()[0] > 0

    def sampling(self) -> Tuple[Dict[int, int], Dict[int, List[Tuple[int, str, str, int]]], Dict[int, str]]:
        self.require("COMPOSITE_EVENTS", ["id", "globalTid"])
        self.require("SAMPLING_CALLCHAINS", ["id", "symbol", "module", "kernelMode", "stackDepth"])
        self.require("ThreadNames", ["nameId", "globalTid"])
        S = self.strings()
        samples = {i: tid for i, tid in self.con.execute("select id, globalTid from COMPOSITE_EVENTS")}
        frames: Dict[int, List] = {}
        for cid, sym, mod, km, depth in self.con.execute(
                "select id, symbol, module, kernelMode, stackDepth from SAMPLING_CALLCHAINS"):
            frames.setdefault(cid, []).append((depth, S.get(sym), S.get(mod), km))
        names = {tid: S.get(n, "?") for n, tid in self.con.execute("select nameId, globalTid from ThreadNames")}
        return samples, frames, names
