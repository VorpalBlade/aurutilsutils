"""Argument parsing and related things"""
from aurutilsutils.utils import get_version


def add_standard_flags(parser):
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
