# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
import io
from unittest import mock

import pytest

import archspec
import archspec.cli
import archspec.cpu
import archspec.cpu.detect


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


def test_cli_why_not_unknown_target():
    """Tests that --why-not with a target name that doesn't exist in TARGETS returns 0 and
    prints a message that includes the unknown name.
    """
    with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
        result = archspec.cli.main(["cpu", "--why-not", "not_a_real_target_xyz"])
    assert result == 0
    assert "not_a_real_target_xyz" in stdout.getvalue()


def test_cli_why_not_valid_target(monkeypatch):
    """Tests that --why-not with a valid target returns 0 and prints a non-empty explanation."""
    monkeypatch.setattr(archspec.cpu.detect, "host", lambda: archspec.cpu.TARGETS["broadwell"])
    with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
        result = archspec.cli.main(["cpu", "--why-not", "haswell"])
    assert result == 0
    assert stdout.getvalue().strip()
