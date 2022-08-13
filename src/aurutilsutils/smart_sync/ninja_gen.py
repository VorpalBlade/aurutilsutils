import shlex
from collections.abc import Collection, Mapping
from pathlib import Path

import networkx as nx

from ..utils.pacman import FileRepo
from ..utils.settings import PackageSettings


def gen_build_rule(chroot: bool, force: bool):
    yield f"rule aurbuild_{chroot}_{force}"
    args = ["--clean", "--syncdeps", "-d", "${repo}", "--root", "${root}"]
    if chroot:
        args.append("--chroot")
    else:
        args.append("--rmdeps")
    if force:
        args.append("--force")
    yield "    command = env -C ${directory} -- aur build " + " ".join(
        args
    ) + " ${build_flags} && date --rfc-3339=ns > ${out}"
    yield "    pool = console"


def gen_build_command(
    package: str,
    pkgbuild_dir: Path,
    repo: FileRepo,
    package_config: PackageSettings,
    force: bool,
    depends: list[str],
):
    fmt_depends = " ".join(f"{d}.stamp" for d in depends)
    pkgbuild_path = pkgbuild_dir / "PKGBUILD"
    yield f"build {package}.stamp: aurbuild_{package_config['chroot']}_{force} {pkgbuild_path} | {fmt_depends}"
    yield f"    directory = {str(pkgbuild_dir)}"
    yield f"    repo = {repo.name}"
    yield f"    root = {repo.root}"
    yield f"    build_flags = {' '.join(shlex.quote(e) for e in package_config['build_flags'])}"


def generate(
    packages: Collection[str],
    repos: Mapping[str, FileRepo],
    configs: Mapping[str, PackageSettings],
    dependency_graph: nx.DiGraph,
    src_dir: Path,
    forced: Collection[str],
):
    """Generate ninja build file

    :param packages: Packages to process
    :param repos: Repository descriptions
    :param configs: Package configurations to determine home repos and chroot status
    :param dependency_graph: Dependency graph to use for ninja
    :param src_dir: This should be aurdest()
    :param forced: Forced packages
    :return: File contents
    """

    def _generator():
        yield from gen_build_rule(False, False)
        yield from gen_build_rule(True, False)
        yield from gen_build_rule(False, True)
        yield from gen_build_rule(True, True)
        for package in sorted(packages):
            cfg = configs[package]
            repo = cfg["repo"]
            yield from gen_build_command(
                package=package,
                pkgbuild_dir=src_dir / package,
                repo=repos[repo],
                package_config=cfg,
                depends=nx.ancestors(dependency_graph, package).intersection(packages),
                force=package in forced,
            )

    return "\n".join(_generator()) + "\n"
