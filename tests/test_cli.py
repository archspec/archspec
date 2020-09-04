# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
import click.testing
import pytest
import re

import archspec
import archspec.cpu
import archspec.cli


@pytest.mark.parametrize("cli_args", [("--help",), ("cpu", "--help")])
def test_command_run_without_failure(cli_args):
    runner = click.testing.CliRunner()
    result = runner.invoke(archspec.cli.main, cli_args)
    assert result.exit_code == 0


@pytest.mark.parametrize("cli_args", [("cpu"), ("cpu --name")])
def test_cli_cpu_name(cli_args):
    runner = click.testing.CliRunner()
    result = runner.invoke(archspec.cli.main, cli_args)
    assert result.exit_code == 0
    assert result.stdout.strip() in archspec.cpu.TARGETS


def test_cli_cpu_dag():
    runner = click.testing.CliRunner()
    result = runner.invoke(archspec.cli.main, ("cpu", "--dag"))
    assert result.exit_code == 0

    assert result.stdout.startswith("digraph {")

    for key in archspec.cpu.TARGETS:
        uarch = archspec.cpu.TARGETS[key]
        # a label is set for every CPU microarchitecture
        # examples:
        #   x86_64 [label=x86_64]
        #   power9 [label=power9]
        #   haswell [label=haswell]
        #   nocona [label="nocona (GenuineIntel)"]
        assert re.search(
            r"^\s+" + uarch.name + r"\s+\[label=.+\]$", result.stdout, re.M
        )
        # every non-generic CPU microarchitecture has at least one parent
        # examples:
        #   haswell -> broadwell
        #   x86_64 -> nocona
        #   power7 -> power8
        if uarch.vendor != "generic":
            assert re.search(
                r"^\s+[0-9a-z_]+\s+->\s+" + uarch.name + "$", result.stdout, re.M
            )

    # hard check for a couple of patterns
    patterns = [
        "x86_64 [label=x86_64]",
        "power9 [label=power9]",
        "haswell [label=haswell]",
        'nocona [label="nocona (GenuineIntel)"]',
        "x86_64 -> nocona",
        "power7 -> power8",
        "haswell -> broadwell",
        "cascadelake -> icelake",
        "cannonlake -> icelake",
    ]
    for pattern in patterns:
        assert pattern in result.stdout

    assert result.stdout.endswith("}\n")


def test_cli_version():
    runner = click.testing.CliRunner()
    result = runner.invoke(archspec.cli.main, ("--version"))
    assert result.exit_code == 0
    assert result.stdout == "archspec, version " + archspec.__version__ + "\n"
