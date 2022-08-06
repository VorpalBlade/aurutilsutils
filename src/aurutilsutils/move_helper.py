#!/usr/bin/env python
"""Script to help transition from mono-repo to split declarative repos"""
import argparse
import logging
import sys
import traceback
from pathlib import Path

from more_itertools import flatten
from prompt_toolkit import print_formatted_text, HTML

from .smart_sync.helpers import find_packages_in_config
from .utils.args import add_standard_flags
from .utils.aurutils import PkgInfo
from .utils.errors import FormattedException, UserErrorMessage
from .utils.misc import packages_in_repos_full, resolve_pkgbase
from .utils.pacman import pacman_config, custom_repos, PacmanConfig, FileRepo
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

    # Set up logging
    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(format="%(levelname)s [%(name)s]: %(message)s", level=log_level)
    try:
        # Start actual program logic
        process(args)
    except UserErrorMessage as e:
        if args.debug:
            traceback.print_exception(e)
        print_formatted_text(HTML("<ansired><b>ERROR:</b></ansired>"), e)
        sys.exit(1)
    except FormattedException as e:
        traceback.print_exception(e)
        print_formatted_text(HTML("<ansired><b>UNEXPECTED ERROR:</b></ansired>"), e)
        sys.exit(1)


def create_pacman_conf(sync_config: SyncConfig, base_path: Path | None):
    for repo in sync_config["repositories"].keys():
        print(f"[{repo}]")
        print("SigLevel = Optional TrustAll")
        print(f"Server = file://{base_path / repo}")
        print("")


def move_commands(
    pacconf: PacmanConfig,
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

    for repo, entries in sync_config["repositories"].items():
        # Find all siblings via a jump back and forth to pkgbase
        bases = set(pkg_to_base[e] for e in entries)
        if missing := bases.difference(base_to_pkgs):
            _LOGGER.warning("Can't find the following packages: %r", missing)
        all_entries = set(flatten(base_to_pkgs[e] for e in bases if e in base_to_pkgs))
        target_path = base_path / repo
        print(f"mkdir {target_path}")
        for entry in all_entries:
            file_name = f"{entry}-{pkg_info_by_name[entry].pkgver}-*.pkg.tar.zst"
            print(f"mv {source_path / file_name} {target_path}")
        print(
            f"repo-add {(target_path / repo).with_suffix('.db.tar.gz')} {target_path}/*.pkg.tar.zst"
        )


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
            pacconf=pacconf,
            sync_config=sync_config,
            repos=repos,
            base_path=args.base_path,
            source_path=args.source_path,
        )


if __name__ == "__main__":
    main()