| ups | f | mutation | host release | host ASan | device | verdict |
|---:|---:|---|---|---|---|---|
| 1 | 4 | strip cut to 50% | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 1 | 5 | strip cut to 90% | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 1 | 6 | strip cut to 3 bytes | crash rc=139 | ==4136068==ERROR: AddressSanitizer: heap-buffer-overflow on  | FAIL(err=1) | both reject |
| 1 | 7 | strip cut to 1 byte | crash rc=139 | ==4136186==ERROR: AddressSanitizer: heap-buffer-overflow on  | FAIL(err=1) | both reject |
| 1 | 8 | run codes overshoot the frame by 5 pixels | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 9 | valid; electron at the last pixel | accepted | clean | ok | both accept, identical counts (silent change vs. original) |
| 1 | 10 | valid; 64 random bytes after the closing code | accepted | clean | ok | both accept, identical counts (no effect) |
| 1 | 11 | 1000 bytes of 127-skip codes, frame never closed | crash rc=139 | ==4136379==ERROR: AddressSanitizer: heap-buffer-overflow on  | FAIL(err=1) | both reject |
| 1 | 12 | electron at the last pixel, no closing code | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 1 | 13 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 14 | 8 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 15 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 16 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 17 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 18 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 19 | 8 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 20 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 21 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 22 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 23 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 24 | 8 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 25 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 26 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 27 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 28 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 1 | 29 | 8 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 30 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 31 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 32 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 1 | 33 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 34 | 8 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 35 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 36 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 37 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 38 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 39 | 8 random bit flips | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 1 | 40 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 41 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 42 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 1 | 43 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 44 | 8 random bit flips | accepted | clean | ok | both accept, identical counts (silent change vs. original) |
| 1 | 45 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 46 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 1 | 47 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 4 | strip cut to 50% | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 2 | 5 | strip cut to 90% | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 2 | 6 | strip cut to 3 bytes | crash rc=139 | ==4137613==ERROR: AddressSanitizer: heap-buffer-overflow on  | FAIL(err=1) | both reject |
| 2 | 7 | strip cut to 1 byte | crash rc=139 | ==4137727==ERROR: AddressSanitizer: heap-buffer-overflow on  | FAIL(err=1) | both reject |
| 2 | 8 | run codes overshoot the frame by 5 pixels | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 9 | valid; electron at the last pixel | accepted | clean | ok | both accept, identical counts (silent change vs. original) |
| 2 | 10 | valid; 64 random bytes after the closing code | accepted | clean | ok | both accept, identical counts (no effect) |
| 2 | 11 | 1000 bytes of 127-skip codes, frame never closed | crash rc=139 | ==4137988==ERROR: AddressSanitizer: heap-buffer-overflow on  | FAIL(err=1) | both reject |
| 2 | 12 | electron at the last pixel, no closing code | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 2 | 13 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 14 | 8 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 15 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 16 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 17 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 18 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 19 | 8 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 20 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 21 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 22 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 23 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 24 | 8 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 25 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 26 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 27 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 28 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 2 | 29 | 8 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 30 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 31 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 32 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 2 | 33 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 34 | 8 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 35 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 36 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 37 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 38 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 39 | 8 random bit flips | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 2 | 40 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 41 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 42 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=1) | both reject |
| 2 | 43 | 1 random bit flip | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 44 | 8 random bit flips | accepted | clean | ok | both accept, identical counts (silent change vs. original) |
| 2 | 45 | 64 random bit flips | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 46 | 16 contiguous random bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |
| 2 | 47 | 64 contiguous zero bytes | frame skipped (warning) | clean | FAIL(err=2) | both reject |

```
{
 "ups1": {
  "both accept, identical counts (no effect)": 5,
  "both reject": 41,
  "both accept, identical counts (silent change vs. original)": 2
 },
 "ups2": {
  "both accept, identical counts (no effect)": 5,
  "both reject": 41,
  "both accept, identical counts (silent change vs. original)": 2
 }
}
```

| fixture | ups | host release | host ASan | device |
|---|---:|---|---|---|
| trunc_last | 1 | 47x accepted; 1x crash rc=139 | 47x accepted; 1x asan: ==4140733==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x | 47x ok; 1x FAIL(err=1) |
| trunc_last | 2 | 47x accepted; 1x crash rc=139 | 47x accepted; 1x asan: ==4142565==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x | 47x ok; 1x FAIL(err=1) |
| trunc_file | 1 | 48x crash rc=134 | 48x asan: rc=134 | REFUSED at index: directory 47 strip 0 extends past the end of the file |
| trunc_file | 2 | 48x crash rc=134 | 48x asan: rc=134 | REFUSED at index: directory 47 strip 0 extends past the end of the file |
| empty_strip | 1 | 48x crash rc=134 | 48x asan: rc=134 | REFUSED at index: strips overlap or are empty (LibTIFF may have estimated a byte count) |
| empty_strip | 2 | 48x crash rc=134 | 48x asan: rc=134 | REFUSED at index: strips overlap or are empty (LibTIFF may have estimated a byte count) |
