#!/bin/bash
# Mutation controls for test_driver_v2.py: each mutant of the v2 driver must fail the test; the unmutated copy must pass.
set -u
P=$(cd "$(dirname "$0")/.." && pwd); REPO=$(cd $P/../../../../.. && pwd); PY=${PY:-/Users/alex.konstantinov/.local/bin/python3}
GEN=${1:-/tmp/mc-capwit-20261027/gen_fw_capture}; M=${2:-/tmp/mc-drv2-mutants}; rm -rf $M; mkdir -p $M
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 DRV_TEST_REPO=$REPO
mutant() { # name, old, new
  d=$M/$1; mkdir -p $d/driver $d/scripts; cp $P/driver/capture_witness.py $P/driver/test_driver_v2.py $d/driver/; cp $P/scripts/weight_oracle.py $d/scripts/
  $PY -B - "$P/driver/run_capture_fw_v2.py" "$d/driver/run_capture_fw_v2.py" "$2" "$3" <<'PY'
import sys
s=open(sys.argv[1]).read(); old,new=sys.argv[3],sys.argv[4]
assert s.count(old)==1,(old,s.count(old)); open(sys.argv[2],'w').write(s.replace(old,new))
PY
  [ $? -eq 0 ] || { echo "$1: MUTATION NOT APPLIED"; return; }
  (cd $d/driver && $PY -B test_driver_v2.py $GEN > $d/out.txt 2>&1); rc=$?
  echo "$1: test rc=$rc :: $(grep -E 'AssertionError|NOT REFUSED' $d/out.txt | tail -1 | cut -c1-150)"
}
d=$M/control; mkdir -p $d/driver $d/scripts; cp $P/driver/*.py $d/driver/; cp $P/scripts/weight_oracle.py $d/scripts/; (cd $d/driver && $PY -B test_driver_v2.py $GEN > $d/out.txt 2>&1); echo "control (unmutated copy): rc=$? :: $(grep -E '^PASS' $d/out.txt)"
mutant m1_no_binary_check_at_launch "check(b.is_file() and not b.is_symlink() and sha(b) == pins['binary_sha256'], 'binary differs from the pins at launch')" "pass"
mutant m2_no_staged_input_hash "check(stat.S_ISREG(os.lstat(q).st_mode) and sha(q) == h, 'staged input differs from the pins at launch: ' + name)" "pass"
mutant m3_no_staging_source_check "check(sha(Path(pins['baseline']['dir']) / 'input' / name) == h, 'staging source (baseline input) differs from the pins: ' + name)" "pass"
mutant m4_no_pins_recheck "check(PINS_SHA0 is not None and sha(ROOT / PINS_NAME) == PINS_SHA0, 'the pins file changed since the driver started')" "pass"
mutant m5_no_staged_scope_check "check(names == sorted(pins['input_files']), f'staged native-input scope differs: {names}')" "pass"
mutant m6_no_postrun_binary_check "if after != pins['binary_sha256'] or before != pins['binary_sha256']:" "if False:"
mutant m7_no_final_inventory_verify "and inventory(on / 'capture') == json.loads((on / 'capture-inventory.json').read_text())['files']" ""
mutant m8_no_second_inventory "check(inventory(cap) == inv, 'capture changed while it was being inventoried')" "pass"
mutant m9_no_count_crosscheck "check(n == expected_capture_files(witnesses['coverage']) == 2 + sum(c['files'] for c in witnesses['coverage'].values()), f'capture file count {n} differs from the coverage-derived counts')" "pass"
mutant m10_symlinks_allowed "check(not stat.S_ISLNK(m) and (stat.S_ISREG(m) or stat.S_ISDIR(m)), f'capture contains a symlink or non-regular entry: {q}')" "pass"
mutant m11_witness_exceptions_not_normalised "    except Exception as e: check(False, f'WITNESS_MALFORMED {type(e).__name__}: {e}')" "    except ZeroDivisionError as e: pass"
mutant m12_no_timeout "rc = p.wait(timeout=timeout)" "rc = p.wait()"
mutant m13_no_group_kill_on_exception "except BaseException: _kill_group(p); raise" "except BaseException: raise"
mutant m14_grant_truthy_only "and isinstance(g.get('receipt_sha256'), str) and bool(HEX64.match(g['receipt_sha256'])))" ")"
mutant m15_no_unexpected_normalisation "    except Exception as e: check(False, f'UNEXPECTED {type(e).__name__}: {e}')" "    except ZeroDivisionError: pass"
