#!/usr/bin/env python3
"""technoproj -- placing the shared make fragment, and checking it.

`changelog.py` travels as an installed command. `version.mk` cannot: it is a
make fragment, and `make` has to be able to read it with no network and no
virtualenv active. So it is *copied into* the consuming repository, and the
copy is checked rather than trusted.

    technoproj sync              write script/version.mk from the package
    technoproj check             fail if the copy has drifted (for CI)
    technoproj version           the installed engine version
    technoproj show              this repo's version in every spelling
    technoproj dollup-manifest   build a dollup package from .technoproj
    technoproj release ...       the release process (see release.py)

`sync` is how a repository adopts a new version.mk; `check` in CI is what
stops the copy going stale, which is the failure this package exists to end
-- version.mk was byte-identical in two repositories and Cargo-shaped in
both, including the one with no Cargo.

`release` is the same bargain applied to the step that ships: one procedure,
declared per repository rather than reinvented in each one's workflow.
"""
import argparse
import filecmp
import json
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


def read_technoproj():
    path = root() / ".technoproj"
    try:
        with open(path) as f:
            return json.load(f)
    except OSError as e:
        print("technoproj: cannot read .technoproj (%s)" % e, file=sys.stderr)
        return None
    except ValueError as e:
        print("technoproj: .technoproj is not valid JSON (%s)" % e, file=sys.stderr)
        return None


def project_command(args) -> int:
    from . import version as _version
    proj = read_technoproj()
    if proj is None:
        return 1

    if args.command == "show":
        try:
            v = _version.of(proj)
        except _version.VersionError as e:
            print("technoproj: %s" % e, file=sys.stderr)
            return 1
        for k in ("tag", "body", "base", "semver", "pep440"):
            print("%-8s %s" % (k + ":", v[k]))
        return 0

    from . import dollup as _dollup
    if not args.out:
        print("technoproj: dollup-manifest needs --out DIR", file=sys.stderr)
        return 1
    try:
        path, manifest, files = _dollup.write(
            str(root()), proj, args.out,
            allow_dirty=args.allow_dirty, manifest_only=args.manifest_only)
    except (_dollup.DollupError, _version.VersionError) as e:
        print("technoproj: %s" % e, file=sys.stderr)
        return 1
    print("wrote %s" % path)
    print("  %s %s  (%d file%s)"
          % (manifest["name"], manifest["version"], len(files),
             "" if len(files) == 1 else "s"))
    src = manifest.get("source", {})
    print("  source %s%s" % (src.get("commit", "?")[:12],
                             "  DIRTY" if src.get("dirty") else ""))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="technoproj", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    for name, help_ in (("sync", "write script/version.mk from the package"),
                        ("check", "fail if the copy has drifted (for CI)"),
                        ("version", "the installed engine version"),
                        ("show", "this repo's version in every spelling")):
        sub.add_parser(name, help=help_)

    dm = sub.add_parser("dollup-manifest",
                        help="build a dollup package from .technoproj")
    dm.add_argument("--out", help="directory to build into")
    dm.add_argument("--allow-dirty", action="store_true",
                    help="record a dirty tree instead of refusing")
    dm.add_argument("--manifest-only", action="store_true",
                    help="write the manifest, not the files")

    rel = sub.add_parser("release", help="the release process")
    rsub = rel.add_subparsers(dest="release_command", required=True)
    for name, help_ in (
            ("plan", "what a release of this tree would be"),
            ("preflight", "run every gate CI runs, here, first"),
            ("check-workflow", "the workflow follows the standard contract"),
    ):
        p = rsub.add_parser(name, help=help_)
        if name != "check-workflow":
            p.add_argument("--tag", help="the tag to release "
                                         "(default: .technoproj's)")
        if name == "preflight":
            p.add_argument("--publish", action="store_true",
                           help="the strict gate a publishing run faces; "
                                "without it this is the rehearsal")
    doc = rsub.add_parser("doctor",
                          help="what this repo is missing, and which release "
                               "route is open")
    doc.add_argument("--offline", action="store_true",
                     help="do not ask GitHub anything")
    cut = rsub.add_parser("cut", help="start the release, by dispatch")
    cut.add_argument("--tag", help="the tag to release "
                                   "(default: .technoproj's)")
    cut.add_argument("--ref", help="branch or SHA to build "
                                   "(default: the default branch)")
    cut.add_argument("--publish", action="store_true",
                     help="create the tag and the release; without it the "
                          "run is a rehearsal that publishes nothing")
    cut.add_argument("--yes", action="store_true",
                     help="actually dispatch; without it this only prints "
                          "what it would send")

    args = ap.parse_args(argv)

    if args.command == "release":
        from . import release as _release
        proj = read_technoproj()
        if proj is None:
            return 1
        from . import version as _v
        try:
            return _release.main(proj, args)
        except (_release.ReleaseError, _v.VersionError) as e:
            print("technoproj: %s" % e, file=sys.stderr)
            return 1

    if args.command in ("show", "dollup-manifest"):
        return project_command(args)

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
