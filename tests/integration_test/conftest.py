import os
import sys

# The modules in this directory import their local helpers package as
# `from helpers.xyz import ...` (not a relative/dotted package import), which
# only resolves when tests/integration_test/ itself is on sys.path. Running
# pytest from the repo root (as CI's `pytest tests/` does) does not add it,
# so collection fails with `ModuleNotFoundError: No module named 'helpers'`
# for every file here -- which aborts the entire pytest session, not just
# these files. Inserting this directory explicitly makes collection work
# regardless of the invoking working directory.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
