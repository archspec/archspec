# Copyright 2013-2020 Lawrence Livermore National Security, LLC and other
# Spack and Archspec Project Developers. See the top-level COPYRIGHT file
# for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
import pytest
import click.testing
import archspec.cli


@pytest.mark.parametrize("cli_args", [("--help",), ("cpu", "--help"), ("cpu",)])
def test_command_run_without_failure(cli_args):
    runner = click.testing.CliRunner()
    result = runner.invoke(archspec.cli.main, cli_args)
    assert result.exit_code == 0
