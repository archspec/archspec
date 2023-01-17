# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
import io
from unittest import mock

import pytest
import archspec
import archspec.cli


@pytest.mark.parametrize("cli_args", [("--help",), ("cpu", "--help"), ("cpu",)])
def test_command_run_without_failure(cli_args):
    result = archspec.cli.main(cli_args)
    assert result == 0


def test_cli_version():
    with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
        result = archspec.cli.main(["--version"])
    assert result == 0
    assert stdout.getvalue() == "archspec, version " + archspec.__version__ + "\n"
