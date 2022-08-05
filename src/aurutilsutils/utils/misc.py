from typing import Collection, Mapping

from . import aurutils
from .pacman import FileRepo


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
