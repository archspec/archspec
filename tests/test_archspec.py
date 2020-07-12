# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
from archspec import __version__


def test_version():
    assert __version__ == "0.1.2"
    with open('pyproject.toml') as fp:
        assert 'version = "' + __version__ + '"\n' in fp.read()
