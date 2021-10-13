# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""The "interconnect" package permits to query interconnect architectures.
"""
from .detect import host

__all__ = [
    "host",
    "version_components",
]
