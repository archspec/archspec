# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
import io
from unittest import mock

import pytest

import archspec
import archspec.cli
import archspec.cpu.detect
import archspec.cpu.microarchitecture
import archspec.cpu.schema


@pytest.mark.parametrize("cli_args", [("--help",), ("cpu", "--help"), ("cpu",)])
def test_command_run_without_failure(cli_args):
    result = archspec.cli.main(cli_args)
    assert result == 0


def test_cli_version():
    with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
        result = archspec.cli.main(["--version"])
    assert result == 0
    assert stdout.getvalue() == "archspec, version " + archspec.__version__ + "\n"


def test_cli_error_json_not_exist(monkeypatch, reset_global_state):
    """Tests that when the environment variable ARCHSPEC_CPU_DIR points to a
    wrong location, a comprehensible error message is printed and the return code is non-zero.
    """
    monkeypatch.setenv("ARCHSPEC_CPU_DIR", "/foo")
    reset_global_state()
    result = archspec.cli.main(["cpu"])
    assert result != 0
