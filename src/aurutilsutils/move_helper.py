#!/usr/bin/env python
"""Script to help transition from mono-repo to split declarative repos"""
import argparse
import logging
from pathlib import Path

from more_itertools import flatten, one

from .smart_sync.helpers import find_packages_in_config
from .utils.args import add_standard_flags
from .utils.aurutils import PkgInfo
from .utils.errors import UserErrorMessage
from .utils.misc import (
    packages_in_repos_full,
    resolve_pkgbase,
    logging_and_error_handling,
)
from .utils.pacman import pacman_config, custom_repos, FileRepo
from .utils.settings import load_sync_settings, SyncConfig

_LOGGER = logging.getLogger(name=__name__)


def _create_parser():
    """Create the parser object"""
    parser = argparse.ArgumentParser(
        description="List packages potentially missing from configs"
    )
    parser.add_argument(
        "-s", "--source-path", type=Path, help="Source path for old packages"
    )
    parser.add_argument(
        "-b", "--base-path", required=True, type=Path, help="Base path for repositories"
    )
    parser.add_argument(
        "-o",
        "--operation",
        required=True,
        action="store",
        help="Select operation",
        choices=("pacman.conf", "mv"),
    )
    add_standard_flags(parser)
    return parser


def main():
    parser = _create_parser()
    args = parser.parse_args()

    with logging_and_error_handling(log_level=args.log_level, debug=args.debug):
        # Start actual program logic
        process(args)


def create_pacman_conf(sync_config: SyncConfig, base_path: Path):
    for repo in sync_config["repositories"].keys():
        print(f"[{repo}]")
        print("SigLevel = Optional TrustAll")
        print(f"Server = file://{base_path / repo}")
        print("")


def move_commands(
    sync_config: SyncConfig,
    repos: dict[str, FileRepo],
    base_path: Path,
    source_path: Path,
):
    # Find what is in the repositories we have.
    in_repos = packages_in_repos_full(repos)

    # Try to resolve to pkgbase (aur depends can't use it so we need to use pkgnames in config, not pkgbase)
    pkgs_in_config = find_packages_in_config(sync_config)
    pkgbases_in_config, pkg_to_base = resolve_pkgbase(in_repos, pkgs_in_config)

    # Create inverse mapping
    base_to_pkgs: dict[str, set[str]] = {}
    pkg_info_by_name: dict[str, PkgInfo] = {}
    for pkginfo in in_repos:
        pkg_info_by_name[pkginfo.package] = pkginfo
        base_to_pkgs.setdefault(pkginfo.pkgbase, set()).add(pkginfo.package)

    # Figure out packages to move and generate commands
    for repo, entries in sync_config["repositories"].items():
        target_path = base_path / repo
        # No moving to self!
        if source_path == target_path:
            continue
        # Find all siblings via a jump back and forth to pkgbase
        bases = set(pkg_to_base[e] for e in entries)
        if missing := bases.difference(base_to_pkgs):
            _LOGGER.warning("Can't find the following packages: %r", missing)
        all_entries = set(flatten(base_to_pkgs[e] for e in bases if e in base_to_pkgs))
        # Figure out packages to move
        pkgs_moved = []
        files_moved = []
        for entry in all_entries:
            # Avoid dealing with architecture, just use a glob
            file_name = f"{entry}-{pkg_info_by_name[entry].pkgver}-*.pkg.tar.zst"
            if list(source_path.glob(file_name)):
                pkgs_moved.append(entry)
                files_moved.append(source_path / file_name)
        # If any packages were to be moved, print the commands to do so
        if files_moved:
            print(f"mkdir {target_path}")
            for file in files_moved:
                print(f"mv {file} {target_path}")
            print(
                f"repo-add {(target_path / repo).with_suffix('.db.tar.gz')} {' '.join(str(e) for e in files_moved)}"
            )
            source_repo = one(source_path.glob("*.db.tar.gz"))
            print(f"repo-remove {source_repo} {' '.join(pkgs_moved)}")


def process(args: argparse.Namespace):
    """Main logic: top level"""
    # 1. Load configurations
    sync_config = load_sync_settings()
    pacconf = pacman_config()
    repos = custom_repos(pacconf)

    if args.operation == "pacman.conf":
        create_pacman_conf(sync_config=sync_config, base_path=args.base_path)
    elif args.operation == "mv":
        if args.source_path is None:
            raise UserErrorMessage(
                "Source path (-s) required for mv command generation."
            )
        move_commands(
            sync_config=sync_config,
            repos=repos,
            base_path=args.base_path,
            source_path=args.source_path,
        )


if __name__ == "__main__":
    main()
