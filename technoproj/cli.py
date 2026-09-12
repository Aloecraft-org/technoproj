#!/usr/bin/env python3
"""technoproj -- placing the shared make fragment, and checking it.

`changelog.py` travels as an installed command. `version.mk` cannot: it is a
make fragment, and `make` has to be able to read it with no network and no
virtualenv active. So it is *copied into* the consuming repository, and the
copy is checked rather than trusted.

    technoproj sync     write script/version.mk from the installed package
    technoproj check    fail if the copy has drifted (for CI)
    technoproj version  the installed engine version

That is the whole of it. `sync` is how a repository adopts a new version.mk;
`check` in CI is what stops the copy going stale, which is the failure this
package exists to end -- version.mk was byte-identical in two repositories
and Cargo-shaped in both, including the one with no Cargo.
"""
import argparse
import filecmp
import os
import shutil
import sys
from pathlib import Path

try:                                     # 3.9+ without importlib.resources.files
    from importlib.resources import files as _files
except ImportError:                      # pragma: no cover
    _files = None

TARGET = Path("script") / "version.mk"


def source() -> Path:
    """The version.mk inside the installed package."""
    if _files is not None:
        return Path(str(_files("technoproj") / "data" / "version.mk"))
    return Path(__file__).resolve().parent / "data" / "version.mk"   # pragma: no cover


def root() -> Path:
    return Path(os.environ.get("TECHNO_ROOT") or os.getcwd())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="technoproj", description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["sync", "check", "version"])
    args = ap.parse_args(argv)

    src = source()
    if not src.is_file():
        print("technoproj: packaged version.mk is missing (%s)" % src, file=sys.stderr)
        return 1

    if args.command == "version":
        try:
            from importlib.metadata import version as _v
            print(_v("technoproj"))
        except Exception:                # pragma: no cover
            print("unknown (not installed)")
        return 0

    dest = root() / TARGET

    if args.command == "sync":
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file() and filecmp.cmp(src, dest, shallow=False):
            print("unchanged %s" % TARGET)
            return 0
        shutil.copyfile(src, dest)
        print("wrote %s" % TARGET)
        return 0

    # check
    if not dest.is_file():
        print("technoproj: %s is missing -- run 'technoproj sync'" % TARGET,
              file=sys.stderr)
        return 1
    if filecmp.cmp(src, dest, shallow=False):
        print("OK: %s matches the installed technoproj" % TARGET)
        return 0
    print("technoproj: %s has drifted from the installed technoproj -- "
          "run 'technoproj sync' and commit the result" % TARGET, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
