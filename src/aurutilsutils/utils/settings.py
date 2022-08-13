"""Settings file handling"""
import copy
from collections import ChainMap
from pathlib import Path
from typing import TypedDict

import appdirs
import yaml

from .errors import UserErrorMessage


def load_settings(file: str):
    file_path = Path(appdirs.user_config_dir("aurutilsutils")) / (file + ".yml")
    try:
        with file_path.open(mode="rt") as f:
            return yaml.safe_load(f)
    except FileNotFoundError as e:

        raise UserErrorMessage(
            f"Settings file {file_path} not found! Consult documentation for how to create it."
        ) from e
    except yaml.YAMLError as e:
        raise UserErrorMessage(
            f"Failed to parse settings file {file_path} due to JSON error: {e}"
        ) from e


class PackageSettings(TypedDict, total=False):
    """Settings for a specific package"""

    # Run build in chroot, default true
    chroot: bool
    # Which repo this belongs to. Note! This should not be in config, but is computed internally
    repo: str
    # Build flags. Note! This should not be in config, but is computed internally from repo data
    build_flags: list[str]


class SyncConfig(TypedDict):
    """Sync settings"""

    # A list of flags to always pass to aur-build
    build_flags: dict[str, list[str]]
    # Mapping from repository name to packages in said repository
    repositories: dict[str, list[str]]
    # Package overrides
    package_overrides: dict[str, PackageSettings]


def load_sync_settings() -> SyncConfig:
    """Load the sync configuration file"""
    settings = load_settings("sync")
    _fixup_build_flags(settings)
    _fixup_package_configs(settings)
    return settings


def _fixup_package_configs(sync_config: SyncConfig) -> None:
    """
    Fix up package configs with default values.

    Also add package configs for any package missing them but in the repos section
    """
    build_flags = sync_config["build_flags"]
    pkg_configs = sync_config["package_overrides"]
    # This is the default package settings
    default_package_settings: PackageSettings = {
        "chroot": True,
    }
    for package, data in pkg_configs.items():
        if data is None:
            data = {}
        data2: PackageSettings = dict(ChainMap(data, default_package_settings))
        pkg_configs[package] = data2
    # We annotate each package with the repository it belongs to.
    for repo, entries in sync_config["repositories"].items():
        for pkg in entries:
            if pkg not in pkg_configs:
                pkg_configs[pkg] = copy.copy(default_package_settings)
            pkg_configs[pkg]["repo"] = repo
            pkg_configs[pkg]["build_flags"] = build_flags[repo]


def _fixup_build_flags(sync_config: SyncConfig) -> None:
    """Resolve everything and add missing entries for build flags"""
    build_flags = sync_config.setdefault("build_flags", {})
    global_flags = build_flags.setdefault("global", [])
    default_flags = build_flags.setdefault("default", [])
    for repo in sync_config["repositories"].keys():
        if repo in {"global", "default"}:
            raise UserErrorMessage(
                f"Forbidden repository name {repo}, this name has special meaning"
            )
        repo_config = build_flags.setdefault(repo, copy.copy(default_flags))
        repo_config.extend(global_flags)
