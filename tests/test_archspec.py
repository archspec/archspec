# Copyright 2013-2020 Lawrence Livermore National Security, LLC and other
# Spack and Archspec Project Developers. See the top-level COPYRIGHT file 
# for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
from archspec import __version__


def test_version():
    assert __version__ == "0.1.0"
