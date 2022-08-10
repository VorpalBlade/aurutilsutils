"""Utilities for using aurutils"""
import dataclasses
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Collection, Mapping

import appdirs
import networkx as nx

from .errors import CommandException, InternalError
from .pacman import FileRepo
from .shell import run_out, run_inout, run_in, run

_LOGGER = logging.getLogger(name=__name__)


def file_ignores():
    """Load file based ignore list from aurutils"""
    ignore_file = Path(appdirs.user_config_dir("aurutils")) / "sync/ignore"
    if not ignore_file.exists():
        return []
    with ignore_file.open(mode="rt", encoding="utf-8") as f:
        # TODO: Not proper syntax (ini-like)
        return f.readlines()
        # TODO: Use this file


def aurdest() -> Path:
    """Get AURDEST directory"""
    if result := os.getenv("AURDEST"):
        return Path(result)
    return Path(appdirs.user_cache_dir("aurutils")) / "sync"


def order_file() -> Path:
    """Path to order file for diffs"""
    return Path(appdirs.user_config_dir("aurutils")) / "sync/orderfile"


def list_repo(repo: FileRepo) -> dict[str, str]:
    """Dict of package names to versions in the given repo"""
    output = run_out(
        ["aur", "repo", "--list", f"--database={repo.name}", f"--root={repo.root}"]
    )
    return dict(tuple[str, str](e.split("\t", maxsplit=1)) for e in output.splitlines())


@dataclasses.dataclass(frozen=True)
class PkgInfo:
    package: str
    depends: str
    pkgbase: str
    pkgver: str


def list_repo_full(repo: FileRepo):
    """List all package info in the given local file repo"""
    output = run_out(
        ["aur", "repo", "--table", f"--database={repo.name}", f"--root={repo.root}"]
    )
    for line in output.splitlines():
        if not line:
            continue
        sline = line.split("\t")
        yield PkgInfo(
            package=sline[0],
            depends=sline[1],
            pkgbase=sline[2],
            pkgver=sline[3],
        )


def vercmp(packages: Mapping[str, str]) -> list[str]:
    """Find outdated packages from AUR"""
    output, _ = run_inout(
        ["aur", "vercmp", "--quiet"],
        "\n".join(f"{k}\t{v}" for k, v in packages.items()),
    )
    return output.splitlines()


def vercmp_are_current(
    packages: Mapping[str, str], in_repos: Mapping[str, str]
) -> list[str]:
    """Find packages that are already up-to-date locally"""
    with tempfile.NamedTemporaryFile(mode="w+t") as in_repos_file:
        in_repos_file.writelines(f"{k}\t{v}\n" for k, v in in_repos.items())
        in_repos_file.write("\n")
        in_repos_file.flush()
        output, _ = run_inout(
            ["aur", "vercmp", f"--path={in_repos_file.name}", "--current"],
            "\n".join(f"{k}\t{v}" for k, v in packages.items()),
        )
    return output.splitlines()


@dataclasses.dataclass(frozen=True)
class DependencyInfo:
    package: str
    depends: str
    pkgbase: str
    pkgver: str
    depends_type: str


def depends(packages: Collection[str]):
    # output = _test_data.splitlines()
    output, _ = run_inout(
        ["aur", "depends", "--table", "-"], "\n".join(packages) + "\n"
    )
    for line in output.splitlines():
        if not line:
            continue
        sline = line.split("\t")
        yield DependencyInfo(
            package=sline[0],
            depends=sline[1],
            pkgbase=sline[2],
            pkgver=sline[3],
            depends_type=sline[4],
        )


def find_provides(dependency_info: set[DependencyInfo]):
    """Find provides that can replace the listed dependencies"""
    output, stderr = run_inout(
        ["aur", "repo-filter", "--sync"],
        "\n".join(set(e.package for e in dependency_info)) + "\n",
    )
    for line in stderr.splitlines():
        _LOGGER.info("Provides: %s", line)
    return set(output.splitlines())


def fetch(queue: Collection[str]):
    """Implements the aur fetch call"""
    with tempfile.NamedTemporaryFile(mode="rt") as results_file:
        run_in(
            [
                "aur",
                "fetch",
                "--sync=auto",
                "--discard",
                f"--results={results_file.name}",
                "-",
            ],
            "\n".join(queue) + "\n",
            cwd=aurdest(),
        )
        results: list[str] = [e.strip() for e in results_file.readlines()]

    def _gen():
        for line in results:
            action, head_from, head_to, path = line.split(":", maxsplit=3)
            yield action, head_from, head_to, Path(path.removeprefix("file://"))

    final_results = list(_gen())

    for act, _, _, p in final_results:
        if act == "clone":
            run(["git", "-C", str(p), "config", "diff.orderFile", str(order_file())])

    return final_results


def view(packages: Collection[str]) -> bool:
    """Implements calls to aur view"""
    with tempfile.NamedTemporaryFile(mode="wt") as queue_file:
        queue_file.write("\n".join(packages))
        queue_file.write("\n")
        queue_file.flush()
        proc = subprocess.run(
            ["aur", "view", f"--arg-file={queue_file.name}"],
            capture_output=False,
            cwd=aurdest(),
        )
        return proc.returncode == 0


def graph(packages: Collection[str]):
    # Read in all .SRCINFO files and concatenate them
    aur_dest = aurdest()
    lines: list[str] = []
    for package in packages:
        with (aur_dest / package / ".SRCINFO").open(mode="rt", encoding="utf-8") as f:
            lines.extend(e.rstrip("\n") for e in f.readlines())
    # Feed this data to aur-graph:
    try:
        out, err = run_inout(["aur", "graph"], input_data="\n".join(lines) + "\n")
    except CommandException as e:
        raise InternalError("Failed to verify dependency graph") from e
    # Build a dependency graph
    g = nx.DiGraph()
    for line in out.splitlines():
        partial_ordering = line.split("\t")
        assert len(partial_ordering) == 2
        if partial_ordering[0] == partial_ordering[1]:
            g.add_node(partial_ordering[0])
            continue
        g.add_edge(partial_ordering[1], partial_ordering[0])
    return g


def vercmp_devel(repos: Mapping[str, FileRepo]):
    """Find set of outdated packages"""
    # Run in parallel for speed
    results = [
        (
            repo,
            subprocess.Popen(
                ["aur", "vercmp-devel", "-d", repo],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                encoding="utf-8",
            ),
        )
        for repo in repos.keys()
    ]
    for repo, result in results:
        stdout, stderr = result.communicate()
        if result.returncode != 0:
            raise CommandException(
                f"aur vercmp-devel failed for repo {repo}", result.returncode, stderr
            )
        for line in stdout.splitlines():
            pkg, _ = line.split(" ", maxsplit=1)
            yield pkg
