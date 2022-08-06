import contextlib
import logging
import sys
import traceback
from typing import Collection, Mapping

from prompt_toolkit import print_formatted_text, HTML

from . import aurutils
from .errors import UserErrorMessage, FormattedException
from .pacman import FileRepo

_LOGGER = logging.getLogger(name=__name__)


def pkgbase_mapping(
    depends: Collection[aurutils.DependencyInfo],
) -> dict[str, set[str]]:
    """Build a mapping from pkgbase to pkg names based on info from aur-depends

    :return: Mapping from pkgbase to set of package names
    """
    pkg_base_rev_map: dict[str, set[str]] = {}
    for entry in depends:
        pkg_base_rev_map.setdefault(entry.pkgbase, set()).add(entry.package)
    return pkg_base_rev_map


def packages_in_repos(
    repos: Mapping[str, FileRepo], *, ignored_repos: Collection[str] = ()
) -> dict[str, str]:
    """Find packages in local repositories on disk

    :param repos: File repositories found in pacman.conf
    :param ignored_repos: Repos ignored on the command line.

    :return Mapping from package name to package version
    """
    in_repos: dict[str, str] = {}
    for repo in repos.values():
        if repo in ignored_repos:
            continue
        in_repos.update(aurutils.list_repo(repo))
    return in_repos


def packages_in_repos_full(
    repos: Mapping[str, FileRepo], *, ignored_repos: Collection[str] = ()
) -> set[aurutils.PkgInfo]:
    """Find packages in local repositories on disk with full info

    :param repos: File repositories found in pacman.conf
    :param ignored_repos: Repos ignored on the command line.

    :return Mapping from package name to package version
    """
    in_repos: set[aurutils.PkgInfo] = set()
    for repo in repos.values():
        if repo in ignored_repos:
            continue
        in_repos.update(aurutils.list_repo_full(repo))
    return in_repos


def resolve_pkgbase(
    in_repos: Collection[aurutils.PkgInfo], pkgs_in_config: Collection[str]
) -> tuple[set[str], dict[str, str]]:
    """Attempt to resolve pkgbase info, first using local info, and then reaching out to aur

    :param in_repos: Information on packages in local repositories
    :param pkgs_in_config: Packages in config we want to find pkgbase names for

    :return: Set of pkgbases corresponding to pkgs_in_config, and mapping from pkgname to pkgbase
    """
    pkg_base_mapping: dict[str, str] = dict((e.package, e.pkgbase) for e in in_repos)
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
        pkg_base_mapping.update(pkg_base_mapping2)
    return pkgbases_in_config, pkg_base_mapping


@contextlib.contextmanager
def logging_and_error_handling(*, log_level: str, debug: bool):
    # Set up logging
    log_level = getattr(logging, log_level.upper())
    logging.basicConfig(format="%(levelname)s [%(name)s]: %(message)s", level=log_level)
    try:
        yield
    except UserErrorMessage as e:
        if debug:
            traceback.print_exception(e)
        print_formatted_text(HTML("<ansired><b>ERROR:</b></ansired>"), e)
        sys.exit(1)
    except FormattedException as e:
        traceback.print_exception(e)
        print_formatted_text(HTML("<ansired><b>UNEXPECTED ERROR:</b></ansired>"), e)
        sys.exit(1)
