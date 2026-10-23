# Runs an author script unmodified, redirecting only its /tmp mkdtemp into the review scratch dir.
import os, runpy, sys, tempfile
_orig = tempfile.mkdtemp
tempfile.mkdtemp = lambda prefix=None, dir=None, **k: _orig(prefix=prefix, dir=os.environ['REVIEW_SCRATCH'])
script = sys.argv[1]; sys.argv = sys.argv[1:]
runpy.run_path(script, run_name='__main__')
