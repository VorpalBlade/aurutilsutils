import logging
from typing import Mapping

from ..utils.pacman import FileRepo
from ..utils.settings import SyncConfig

_LOGGER = logging.getLogger(name=__name__)


def find_packages_to_have(
    repos: Mapping[str, FileRepo], sync_config: SyncConfig
) -> set[str]:
    """Find all packages we should have according to the config (and repositories that exist on this machine).

    :param repos: Repositories on this machine
    :param sync_config: Sync config with everything that should exist
    :return: Set of AUR packages that we should have
    """
    results = set()
    for repo, entries in sync_config["repositories"].items():
        if repo not in repos:
            _LOGGER.info("Skipping %s: repo doesn't exist on this machine", repo)
            continue
        results.update(entries)
    return results


def find_packages_in_config(sync_config: SyncConfig) -> set[str]:
    """Find all packages mentioned in the config (even if we don't have them).

    :param sync_config: Sync config with everything that should exist
    :return: Set of AUR packages that we should have
    """
    results = set()
    for entries in sync_config["repositories"].values():
        results.update(entries)
    return results
