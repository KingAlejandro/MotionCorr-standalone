The metadata-writing inline script emitted one Python SyntaxWarning for a shell escape in the
initial command-summary string and exited 0. COMMANDS.json now uses argv vectors for those Git
commands. No ancestry probe, identity finding or process-suite status was affected. The actual
failed ancestry inspection is separately retained as inspection-01-FAIL.json.
