#!/bin/bash
exec taskset -c 88-95 "$MC_BIN" "$@"
