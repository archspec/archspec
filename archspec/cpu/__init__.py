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
    InvalidCompilerVersion,
    InvalidRange,
    Microarchitecture,
    MicroarchitectureRange,
    UnsupportedMicroarchitecture,
    generic_microarchitecture,
    microarchitecture_max,
    microarchitecture_min,
    microarchitecture_range,
    version_components,
)

__all__ = [
    "brand_string",
    "host",
    "why_not",
    "TARGETS",
    "InvalidCompilerVersion",
    "InvalidRange",
    "Microarchitecture",
    "MicroarchitectureRange",
    "UnsupportedMicroarchitecture",
    "generic_microarchitecture",
    "microarchitecture_max",
    "microarchitecture_min",
    "microarchitecture_range",
    "version_components",
]
