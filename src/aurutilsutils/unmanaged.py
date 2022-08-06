#!/usr/bin/env python
"""Script to find things that need to be updated in smart-sync config"""
import argparse
import logging
import sys
import traceback

import networkx as nx
from prompt_toolkit import print_formatted_text, HTML

from .smart_sync.helpers import find_packages_in_config
from .utils import aurutils, get_version
from .utils.errors import FormattedException, UserErrorMessage
from .utils.misc import packages_in_repos_full
from .utils.pacman import pacman_config, custom_repos
from .utils.settings import load_sync_settings

_LOGGER = logging.getLogger(name=__name__)


def _create_parser():
    """Create the parser object"""
    parser = argparse.ArgumentParser(
        description="List packages potentially missing from configs"
    )
    parser.add_argument("--version", action="version", version=get_version())
    parser.add_argument(
        "-l",
        "--log-level",
        default="warning",
        action="store",
        help="Set log level",
        choices=("warning", "info", "debug"),
    )
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


def process(args: argparse.Namespace):
    """Main logic: top level"""
    # 1. Load configurations
    sync_config = load_sync_settings()
    pacconf = pacman_config()
    repos = custom_repos(pacconf)
    # 2. Find packages we are supposed to have
    pkgs_in_config = find_packages_in_config(sync_config)
    # 3. Find what is in the repositories we have.
    # Mapping from package name to version string, but we only care about the names here
    in_repos = packages_in_repos_full(repos)
    in_repos_pkgbase = set(e.pkgbase for e in in_repos)

    # Try to resolve to pkgbase (aur depends can't use it so we need to use pkgnames in config, not pkgbase)
    pkg_base_mapping = dict((e.package, e.pkgbase) for e in in_repos)
    pkgbases_in_config = set()
    unknown_in_config = set()
    for e in pkgs_in_config:
        if e in pkg_base_mapping:
            pkgbases_in_config.add(pkg_base_mapping[e])
        else:
            unknown_in_config.add(e)
    # Try resolving the remaining pkgbases using aur depends
    if unknown_in_config:
        depends = set(aurutils.depends(unknown_in_config))
        pkg_base_mapping2 = dict((e.package, e.pkgbase) for e in depends)
        for e in unknown_in_config:
            if e in pkg_base_mapping2:
                pkgbases_in_config.add(pkg_base_mapping2[e])
            else:
                _LOGGER.warning(
                    "Unknown package in config: %s (can't find locally or on AUR)", e
                )

    # Just diffing the two sets does not suffice, we need to resolve dependencies next

    # However, not all packages may exist locally in aurdest (which is needed for graph)!
    packages_in_aurdest = set(e.name for e in aurutils.aurdest().iterdir())

    dep_graph = aurutils.graph(in_repos_pkgbase.intersection(packages_in_aurdest))
    dep_graph.add_nodes_from(pkgbases_in_config)

    all_pkgs_to_have = set()
    all_pkgs_to_have.update(pkgbases_in_config)
    for package in pkgbases_in_config:
        all_pkgs_to_have.update(
            nx.ancestors(dep_graph, package).intersection(in_repos_pkgbase)
        )

    # Now we are ready to print
    print_formatted_text(HTML("<b>Missing from config:</b>"))
    for entry in sorted(in_repos_pkgbase.difference(all_pkgs_to_have)):
        print(f" - {entry}")


if __name__ == "__main__":
    main()
