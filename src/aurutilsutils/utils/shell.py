"""Utilities to run commands in a less painful way than raw subprocess calls

This wraps subprocess
"""

import subprocess
import sys

from .errors import CommandException


def run(cmd: list[str]):
    proc = subprocess.run(
        cmd,
    )
    if proc.returncode != 0:
        raise CommandException(cmd, proc.returncode, "")


def run_out(cmd: list[str]) -> str:
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise CommandException(cmd, proc.returncode, proc.stderr)
    return proc.stdout


def run_inout(cmd: list[str], input_data: str, *, cwd=None) -> tuple[str, str]:
    """Feed process input and return output"""
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        cwd=cwd,
    )
    stdout, stderr = proc.communicate(input=input_data)
    if proc.returncode != 0:
        raise CommandException(cmd, proc.returncode, stderr)
    return stdout, stderr


def run_in(cmd: list[str], input_data: str, *, cwd=None):
    """Feed process input and return output"""
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=sys.stdout,
        stderr=sys.stderr,
        encoding="utf-8",
        cwd=cwd,
    )
    proc.communicate(input_data)
    if proc.returncode != 0:
        raise CommandException(cmd, proc.returncode, "")
