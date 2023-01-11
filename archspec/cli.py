# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""
archspec command line interface
"""

import argparse
import typing

import click

import archspec
import archspec.cpu


class ErrorCatchingArgumentParser(argparse.ArgumentParser):
    """An `ArgumentParser` that doesn't exit by itself.
    """

    def exit(self, status=0, message=None):
        if status:
            raise argparse.ArgumentError(None, message)


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        "archspec",
        description="archspec command line interface",
        add_help=False,
        exit_on_error=False,
    )
    parser.add_argument(
        "--version",
        "-V",
        help="Show the version and exit.",
        action="version",
        version="archspec, version {}".format(archspec.__version__),
    )
    parser.add_argument(
        "--help",
        "-h",
        help="Show the help and exit.",
        action="help"
    )

    subcommands = parser.add_subparsers(
        title="command",
        metavar="COMMAND",
        dest="command",
    )

    cpu_command = subcommands.add_parser(
        "cpu",
        description="archspec command line interface for CPU",
    )
    cpu_command.set_defaults(run=cpu)

    return parser


def cpu(args: argparse.Namespace) -> int:
    print(archspec.cpu.host())
    return 0


def main(argv: typing.Optional[typing.List[str]] = None) -> int:
    parser = _make_parser()

    try:
        args = parser.parse_args(argv)
    except SystemExit as err:
        return err.code

    if args.command is None:
        parser.print_help()
        return 0

    return args.run(args)

