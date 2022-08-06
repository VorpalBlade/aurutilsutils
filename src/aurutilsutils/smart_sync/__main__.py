#!/usr/bin/env python
import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from collections.abc import Collection, Mapping
from pathlib import Path

import networkx as nx
import regex
from more_itertools import flatten, one, unique_everseen
from prompt_toolkit import print_formatted_text, HTML

from . import ninja_gen
from .helpers import find_packages_to_have
from ..utils import aurutils, get_version
from ..utils.errors import UserErrorMessage, FormattedException, CommandException
from ..utils.misc import pkgbase_mapping, packages_in_repos
from ..utils.pacman import pacman_config, custom_repos, FileRepo
from ..utils.settings import (
    load_sync_settings,
    PackageSettings,
    SyncConfig,
)

_LOGGER = logging.getLogger(name=__name__)


def _create_parser():
    """Create the parser object"""
    parser = argparse.ArgumentParser(description="Smart declarative sync")
    parser.add_argument(
        "-u", "--update", default=False, action="store_true", help="Run update"
    )
    parser.add_argument(
        "-V",
        "--vcs",
        default=False,
        action="store_true",
        help="Check for VCS packages that needs to be updated",
    )
    parser.add_argument(
        "-i",
        "--ignore",
        default=[],
        action="append",
        metavar="PACKAGE",
        help="Packages to skip during this run",
    )
    parser.add_argument(
        "--no-download",
        dest="download",
        default=True,
        action="store_false",
        help="Do not download packages",
    )
    parser.add_argument(
        "--no-view",
        dest="view",
        default=True,
        action="store_false",
        help="Do not view packages (DANGEROUS!)",
    )
    parser.add_argument(
        "--no-build",
        dest="build",
        default=True,
        action="store_false",
        help="Do not perform actual build",
    )
    parser.add_argument(
        "--ignore-repo",
        default=[],
        action="append",
        metavar="REPOSITORY",
        help="Repositories to skip during this run",
    )
    parser.add_argument(
        "--force-rebuild",
        default=[],
        nargs="+",
        action="append",
        metavar="PACKAGE",
        help="Package to force rebuilding",
    )
    parser.add_argument("--version", action="version", version=get_version())
    group = parser.add_argument_group(title="Output control")
    group.add_argument(
        "-d", "--debug", default=False, action="store_true", help="Show debug output"
    )
    group.add_argument(
        "-l",
        "--log-level",
        default="warning",
        action="store",
        help="Set log level",
        choices=("warning", "info", "debug"),
    )
    return parser


def main():
    """Main entry point of aur smartsync"""
    # Parse arguments
    parser = _create_parser()
    args = parser.parse_args()
    args.force_rebuild = set(flatten(args.force_rebuild))

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
    """Main program: the top level code"""
    # 1. Load configurations
    sync_config = load_sync_settings()
    pacconf = pacman_config()
    repos = custom_repos(pacconf)
    _LOGGER.debug("Repos: %r", repos.keys())
    # Sets of targets to process and things to skip
    ignored = set()
    ignored.update(args.ignore)
    # Build up list of packages to have. We should have everything we have the repository for.
    pkgs_to_have = find_packages_to_have(repos, sync_config)
    _LOGGER.debug(f"End of step 1: pkgs_to_have=%r", pkgs_to_have)
    # 2. Find what is in the repositories we have.
    # Mapping from package name to version string
    in_repos = packages_in_repos(repos, ignored_repos=args.ignore_repo)
    # 3. Find packages to process (packages in config missing (but repo exists) + update + devel)
    targets: set[str] = set()
    # Add missing packages
    targets.update(pkgs_to_have.difference(in_repos.keys()))
    # Add out-of-date packages (this may include things that shouldn't be
    # in the repos to begin with, that will get filtered later)
    if args.update:
        targets.update(
            aurutils.vercmp(
                dict((k, v) for k, v in in_repos.items() if k not in ignored)
            )
        )
    # Add out-of-date VCS packages
    if args.vcs:
        # TODO: Find out of date VCS packages
        pass
    # Add force rebuild packages
    targets.update(args.force_rebuild)
    _LOGGER.debug("End of step 3: targets=%r, ignored=%r", targets, ignored)
    # 4. Resolve dependency info
    if not targets:
        print_formatted_text(HTML("<b>Exiting early</b>: Nothing to do!"))
        sys.exit(0)
    try:
        depends = set(aurutils.depends(targets))
    except CommandException as e:
        raise UserErrorMessage(
            "Unexpected error when running aur depends (check for typos in package names)."
            " Another possibility is that the package is too new to be available via the API yet.\n"
            f"Command attempted: aur depends --table {' '.join(targets)}"
        ) from e
    # 5. Filter out:
    filter_set = set()
    #    * Ignored packages & repositories from the command line.
    filter_set.update(ignored)
    #    * Packages that are already up-to-date
    current_packages = set(
        aurutils.vercmp_are_current(
            packages=dict((e.package, e.pkgver) for e in depends), in_repos=in_repos
        )
    )
    filter_set.update(current_packages)
    #    * Things already handled by provides
    filter_set.update(aurutils.find_provides(depends))
    #    * Useless dependencies that shouldn't be included any longer
    # TODO!
    #    * But we do want to build force-rebuild entries
    filter_set.difference_update(args.force_rebuild)
    targets_depends = set(e.pkgbase for e in depends)
    targets_depends.difference_update(filter_set)
    _LOGGER.debug(
        "End of step 5: target_depends=%r, filter_set=%r",
        targets_depends,
        filter_set,
    )
    # 6. Download packages
    if args.download:
        aurutils.fetch(targets_depends)
    # 7. Call aur view to show user what will be done
    if args.view:
        if not aurutils.view(targets_depends):
            print_formatted_text(
                HTML("<b>User aborted</b> (aur view returned non-zero)")
            )
            sys.exit(1)
    # 8. Rebuild dependency info with .SRCINFO data (needed to handle .so deps and versioned deps)
    dep_graph = aurutils.graph(targets_depends)
    if not nx.is_directed_acyclic_graph(dep_graph):
        raise UserErrorMessage("AIEE! Cycles in dependency graph! Giving up!")
    # 9. Build pkgbase mapping
    pkg_base_rev_map = pkgbase_mapping(depends)
    # 10. Figure out settings for each package (for aur build)
    build_settings = generate_build_settings(
        dep_graph, pkg_base_rev_map, sync_config, targets_depends
    )
    _LOGGER.debug("End of step 10: build_settings=%r", build_settings)
    # 11. Build a ninja file
    build_with_ninja(
        args, build_settings, dep_graph, targets_depends, repos, sync_config
    )


def generate_build_settings(
    dep_graph: nx.DiGraph,
    pkg_base_rev_map: dict[str, set[str]],
    sync_config: SyncConfig,
    targets_depends: set[str],
):
    """Figure out build settings for each package. For packages in the config this is easy.
    This tries to figure out sensible settings for dependencies as well.

    :param dep_graph: The dependency graph
    :param pkg_base_rev_map: Mapping from pkgbase to package names
    :param sync_config: Program config
    :param targets_depends: Packages we are planning to build
    :return: A mapping from pkgbase to build settings for those packages.
    """
    build_settings: dict[str, PackageSettings] = {}
    pkg_configs = sync_config["package_overrides"]
    for target in targets_depends:
        pkg_names = pkg_base_rev_map[target]
        possible_pconfs = filter(
            lambda x: x is not None,
            (pkg_configs.get(pname, None) for pname in pkg_names),
        )
        pconfs = list(unique_everseen(possible_pconfs))

        if len(pconfs) == 1:
            pconf = one(pconfs)
            build_settings[target] = pconf
        elif len(pconfs) == 0:
            # This is pulled in as a dependency of something, figure out what
            parents = nx.descendants(dep_graph, target)
            _LOGGER.debug("Dependency %s, found %r as parents", target, parents)
            # Figure out which repository it should go in.
            repo_candidates = set(
                pkg_configs[e]["repo"] for e in parents if e in pkg_configs
            )
            if len(repo_candidates) != 1:
                raise UserErrorMessage(
                    f"Package {target} is pulled in as a dependency, but it isn't clear which repo to put it. "
                    f"Candidates are: {repo_candidates}. "
                    "Manual configuration required"
                )
            # Assume chroot okay unless overridden
            build_settings[target] = {"repo": one(repo_candidates), "chroot": True}
        else:
            raise UserErrorMessage(
                f"Inconsistent configurations found for (possibly split?) package {target}: {pconfs}"
            )
    return build_settings


def build_with_ninja(
    args: argparse.Namespace,
    build_settings: Mapping[str, PackageSettings],
    dep_graph: nx.DiGraph,
    package_queue: Collection[str],
    repos: Mapping[str, FileRepo],
    sync_config: SyncConfig,
):
    """Create a ninja file and build using it

    :param args: Command line arguments
    :param build_settings: Settings for building the packages we expect to build
    :param dep_graph: Dependency graph
    :param package_queue: Queue of packages to build
    :param repos: File repositories from pacman.conf
    :param sync_config: Program configuration
    """
    tmp_base = Path(f"/run/user/{os.getuid()}/aurutilsutils")
    tmp_base.mkdir(parents=True, mode=0o700, exist_ok=True)
    tmp_path = Path(tempfile.mkdtemp(dir=tmp_base, prefix="ninja-"))
    build_success = False
    try:
        ninja_contents = ninja_gen.generate(
            packages=package_queue,
            repos=repos,
            configs=build_settings,
            dependency_graph=dep_graph,
            src_dir=aurutils.aurdest(),
            build_flags=sync_config["build_flags"],
            forced=args.force_rebuild,
        )
        with (tmp_path / "build.ninja").open(mode="wt") as f:
            f.write(ninja_contents)
        print(f"Temporary ninja directory: {tmp_path}")
        if args.build:
            result = subprocess.run(
                ["ninja", "-k0"],
                cwd=tmp_path,
                env={"NINJA_STATUS": "[%s/%t] ", **os.environ},
            )
            if result.returncode == 0:
                build_success = True
            else:
                print_formatted_text(HTML("<ansired><b>Build failed</b></ansired>"))
                print(f"---")
                print(f"    Temporary ninja directory: {tmp_path}")
                print(f"---")
                new_result = subprocess.run(
                    [
                        "ninja",
                        "-n",
                        "-C",
                        "/var/empty",
                        "-f",
                        str(tmp_path / "build.ninja"),
                    ],
                    env={"NINJA_STATUS": "[%s/%t] ", **os.environ},
                    encoding="utf-8",
                    stdout=subprocess.PIPE,
                )
                _RE_STAMP = regex.compile(
                    r"(\[\d+/\d+\] )(.+?)([\w@\.\-\+]+)(\.stamp)", regex.VERSION1
                )
                for line in new_result.stdout.splitlines():
                    if match := _RE_STAMP.search(line):
                        status = match.group(1)
                        pkg = match.group(3)
                        if (tmp_path / pkg).exists():
                            print_formatted_text(
                                HTML(
                                    "{status} <b>{pkg}</b>\t<ansigreen>OK</ansigreen>"
                                ).format(status=status, pkg=pkg)
                            )
                        else:
                            print_formatted_text(
                                HTML(
                                    "{status} <b>{pkg}</b>\t<ansired>FAIL</ansired>"
                                ).format(status=status, pkg=pkg)
                            )
    finally:
        if not args.debug and args.build and build_success:
            shutil.rmtree(tmp_path)


if __name__ == "__main__":
    main()
