#!/usr/bin/env python
"""Script to find things that need to be updated in smart-sync config"""
import argparse
import logging

import networkx as nx
from prompt_toolkit import print_formatted_text, HTML

from .smart_sync.helpers import find_packages_in_config
from .utils import aurutils
from .utils.args import add_standard_flags
from .utils.misc import (
    packages_in_repos_full,
    resolve_pkgbase,
    logging_and_error_handling,
)
from .utils.pacman import pacman_config, custom_repos
from .utils.settings import load_sync_settings

_LOGGER = logging.getLogger(name=__name__)


def _create_parser():
    """Create the parser object"""
    parser = argparse.ArgumentParser(
        description="List packages potentially missing from configs"
    )
    add_standard_flags(parser)
    return parser


def main():
    parser = _create_parser()
    args = parser.parse_args()

    with logging_and_error_handling(log_level=args.log_level, debug=args.debug):
        # Start actual program logic
        process()


def process():
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
    pkgbases_in_config, _ = resolve_pkgbase(in_repos, pkgs_in_config)

    # Just diffing the two sets does not suffice, we need to resolve dependencies next

    # However, not all packages may exist locally in aurdest (which is needed for graph)!
    pkgbases_in_aurdest = set(e.name for e in aurutils.aurdest().iterdir())

    dep_graph = aurutils.graph(in_repos_pkgbase.intersection(pkgbases_in_aurdest))
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
