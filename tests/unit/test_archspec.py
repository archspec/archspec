# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
import archspec


def test_version():
    assert archspec.__version__ == "0.2.5"
    with open("pyproject.toml") as fp:
        assert 'version = "' + archspec.__version__ + '"\n' in fp.read()
