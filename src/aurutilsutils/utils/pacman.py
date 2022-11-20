"""Utilities for dealing with pacman"""
import dataclasses
from collections.abc import Iterable, Generator
from pathlib import Path

import regex

from aurutilsutils.utils.errors import CommandException

# Pattern to find section headers
from aurutilsutils.utils.shell import run_out

_RE_SECTION = regex.compile(r"\[(?P<name>[^\n]+)\].*", regex.VERSION1)

PacmanConfig = dict[str, dict[str, str | list[str] | None]]


def _inner_parse_pacman_config(
    data: Iterable[str],
) -> Generator[tuple[str | None, str, str | None], None, None]:
    """Low level ini-like parser"""
    # We can't use configparser in Python, since pacman has lines with no = in them
    cur_section = None
    for line in data:
        line = line.strip()
        if not line:
            continue
        elif line.startswith("#"):
            continue
        elif match := _RE_SECTION.match(line):
            cur_section = match.group("name")
        else:
            if "=" in line:
                key, value = line.split("=", maxsplit=1)
                yield cur_section, key.strip(), value.strip()
            else:
                yield cur_section, line, None


def _parse_pacman_config(data: Iterable[str]) -> PacmanConfig:
    """High level parser, putting lines into a dictionary"""
    result: PacmanConfig = {}
    for section, key, value in _inner_parse_pacman_config(data):
        sec_obj: dict[str, str | list[str] | None] = result.setdefault(section, {})
        if key not in sec_obj:
            sec_obj[key] = value
        else:
            if not isinstance(sec_obj[key], list):
                sec_obj[key] = [sec_obj[key]]
            sec_obj[key].append(value)
    return result


def pacman_config(*, config_file: str | None = None, raw: bool = False) -> PacmanConfig:
    """Load a pacman.conf file"""
    cmd = ["pacconf"]
    if config_file is not None:
        cmd += [f"--config={config_file}"]
    if raw:
        cmd += ["--raw"]
    return _parse_pacman_config(run_out(cmd).splitlines())


@dataclasses.dataclass(frozen=True)
class FileRepo:
    """Information about a file based repository"""

    # Name of repository
    name: str
    # Root of repository
    root: Path
    # Path to database file of repository
    path: Path


def custom_repos(config: PacmanConfig) -> dict[str, FileRepo]:
    """Extract custom repositories"""
    repos = {}
    for section, data in config.items():
        if section == "options":
            continue
        # This doesn't handle file based repo with multiple servers, but I don't see a use for that.
        if isinstance(data["Server"], str) and data["Server"].startswith("file://"):
            # We found a file based repo!
            root = Path(data["Server"].removeprefix("file://"))
            repos[section] = FileRepo(
                name=section, root=root, path=(root / f"{section}.db").resolve()
            )
    return repos


def find_package_repo(package: str) -> set[tuple[str, str]]:
    """Find which repo a package is in (if any)"""
    try:
        pkg_results = set(
            run_out(["pacman", "-S", "--print", "--print-format", "%r|%n", package])
            .rstrip("\n")
            .split("\n")
        )
        return {tuple(e.split("|")) for e in pkg_results}
    except CommandException as e:
        if e.stderr.contains("not found"):
            return set()
        raise
