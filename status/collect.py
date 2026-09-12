#!/usr/bin/env python3
"""Shim. The collector lives in the installed package as technoproj.status,
so dart2 gets it by `pip install technoproj` rather than by a second copy of
this file rsynced into the fleet -- which is the drift this package exists
to end, and it would have been ironic to reintroduce it here.

This file stays so `status/` is runnable straight from a checkout:

    ./status/collect.py --profile internal --out /tmp/data

On a host with the package installed, the entry point is the same code:

    technoproj-status-collect --profile internal --out /var/www/html/status/data
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from technoproj.status import main   # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
