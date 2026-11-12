# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""The "cpu" package permits to query and compare different
CPU microarchitectures.
"""
from .detect import brand_string, host, why_not
from .microarchitecture import (
    TARGETS,
    ArchspecError,
    InvalidCompilerVersion,
    InvalidRange,
    InvalidType,
    Microarchitecture,
    UnknownMicroarchitecture,
    UnsupportedMicroarchitecture,
    generic_microarchitecture,
    version_components,
)
from .ranges import MicroarchitectureRange, MicroarchitectureRangeList

__all__ = [
    "brand_string",
    "host",
    "why_not",
    "TARGETS",
    "ArchspecError",
    "InvalidCompilerVersion",
    "InvalidRange",
    "InvalidType",
    "Microarchitecture",
    "MicroarchitectureRange",
    "MicroarchitectureRangeList",
    "UnknownMicroarchitecture",
    "UnsupportedMicroarchitecture",
    "generic_microarchitecture",
    "version_components",
]
