# Copyright 2019-2026 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""Defines the GPUMicroarch class, describing a detected GPU microarchitecture."""

# This class deliberately mirrors archspec.cpu.microarchitecture.Microarchitecture so the two
# behave the same; the shared logic is not factored out to keep the CPU module untouched.
# pylint: disable=duplicate-code

import re
import warnings
from typing import Any, Dict, List, Optional, Set

from ..cpu.microarchitecture import (
    InvalidCompilerVersion,
    UnsupportedMicroarchitecture,
    version_components,
)
from .gpu import GPU


class GPUMicroarch:
    """Represents a GPU Microarchitecture"""

    def __init__(
        self,
        name: str = "",
        vendor: str = "",
        parents: Optional[List["GPUMicroarch"]] = None,
        compilers: Optional[Dict[str, List[Dict[str, str]]]] = None,
    ):
        """
        Args:
            name: compatibility identifier name (e.g. ``90`` for NVIDIA, ``gfx90a`` for AMD)
            vendor: name of chip manufacturer (e.g. ``nvidia``)
            parents: list of parent micro-architectures, if any. Parenthood follows binary
                compatibility, not chronology: a micro-architecture runs code built for any of
                its ancestors. For example NVIDIA ``86``, which has ``80`` as a parent, runs
                SASS compiled for ``80``.
            compilers: compiler support to generate code for this micro-architecture. Keys are
                compiler names, values are lists of dictionaries with fields:

                * versions: compiler versions that support this micro-architecture, as a
                    ``min:max`` range where either bound may be empty.
                * flags: flags to be passed to the compiler to target this micro-architecture.
                * name: optional, the micro-architecture name as the compiler spells it. Defaults
                    to ``self.name`` when formatting ``flags``.
        """
        self.name = name
        self.vendor = vendor
        self.parents: List["GPUMicroarch"] = parents or []
        self.compilers: Dict[str, List[Dict[str, str]]] = compilers or {}

        # Cache the "ancestor" computation
        self._ancestors: Optional[List["GPUMicroarch"]] = None
        # Cache the "family" computation
        self._family: Optional["GPUMicroarch"] = None

    @property
    def ancestors(self) -> List["GPUMicroarch"]:
        """All the ancestors of this microarchitecture."""
        if self._ancestors is None:
            value = self.parents[:]
            for parent in self.parents:
                value.extend(a for a in parent.ancestors if a not in value)
            self._ancestors = value
        return self._ancestors

    @property
    def family(self) -> "GPUMicroarch":
        """Returns the architecture family a given target belongs to"""
        if self._family is None:
            roots = [x for x in [self] + self.ancestors if not x.ancestors]
            msg = "a target is expected to belong to just one architecture family"
            msg += f"[found {', '.join(str(x) for x in roots)}]"
            assert len(roots) == 1, msg
            self._family = roots.pop()

        return self._family

    def _to_set(self) -> Set[str]:
        """Returns a set of the nodes in this microarchitecture DAG."""
        # This function is used to implement subset semantics with
        # comparison operators
        return set([str(self)] + [str(x) for x in self.ancestors])

    def __eq__(self, other):
        if not isinstance(other, GPUMicroarch):
            return NotImplemented
        return (
            self.name == other.name
            and self.vendor == other.vendor
            and self.parents == other.parents  # avoid ancestors here
            and self.compilers == other.compilers
        )

    def __ne__(self, other):
        return not self == other

    def __hash__(self) -> int:
        return hash((self.vendor, self.name))

    def __lt__(self, other):
        if not isinstance(other, GPUMicroarch):
            return NotImplemented
        return self._to_set() < other._to_set()

    def __le__(self, other):
        return (self == other) or (self < other)

    def __gt__(self, other):
        if not isinstance(other, GPUMicroarch):
            return NotImplemented
        return self._to_set() > other._to_set()

    def __ge__(self, other):
        return (self == other) or (self > other)

    def __repr__(self) -> str:
        fields = ", ".join(
            f"{field}={value!r}" for field, value in self.to_dict().items() if value
        )
        return f"{self.__class__.__name__}({fields})"

    def __str__(self) -> str:
        if self.name and self.vendor:
            return f"{self.name} ({self.vendor})"
        return "unknown gpu"

    def to_dict(self) -> Dict[str, Any]:
        """Returns a dictionary representation of this object."""
        return {
            "name": self.name,
            "vendor": self.vendor,
            "parents": [str(x.name) for x in self.parents],
            "compilers": self.compilers,
        }

    def optimization_flags(self, compiler: str, version: str) -> str:
        """Returns a string containing the flags that need to be passed to ``compiler`` to
        produce code for this micro-architecture.

        The version is expected to be a string of dot-separated digits.

        If neither this micro-architecture nor any of its ancestors has information on the
        compiler passed as argument, the function returns an empty string. If it is known that
        the compiler version we want to use does not support this architecture, the function
        raises an exception.

        Args:
            compiler: name of the compiler to be used
            version: version of the compiler to be used

        Raises:
            ~archspec.cpu.microarchitecture.UnsupportedMicroarchitecture: if the requested
                compiler does not support this micro-architecture.
            ~archspec.cpu.microarchitecture.InvalidCompilerVersion: if the version doesn't
                match the expected format
        """
        if compiler not in self.compilers:
            # If an ancestor knows the compiler, support stops before this micro-architecture
            known = [x for x in self.ancestors if compiler in x.compilers]
            if not known:
                return ""
            best_target = known[0]
            msg = (
                f"'{compiler}' compiler is known to target up to the '{best_target}'"
                f" microarchitecture in the '{best_target.family}' architecture family"
            )
            raise UnsupportedMicroarchitecture(msg)

        if not re.match(r"^(?:\d+\.)*\d+$", version):
            msg = (
                "invalid format for the compiler version argument. "
                "Only dot separated digits are allowed."
            )
            raise InvalidCompilerVersion(msg)

        compiler_info = self.compilers[compiler]
        for compiler_entry in compiler_info:
            if not _satisfies_version_constraint(compiler_entry["versions"], version):
                continue

            # If there's no field name, use the name of the micro-architecture
            compiler_entry.setdefault("name", self.name)

            warning_message = compiler_entry.get("warnings", None)
            if warning_message:
                warnings.warn(warning_message)

            return compiler_entry["flags"].format(**compiler_entry)

        msg = f"cannot produce binary for micro-architecture '{self.name}'"
        msg += f" with {compiler}@{version}"
        if compiler_info:
            versions = [x["versions"] for x in compiler_info]
            msg += f' [supported compiler versions are {", ".join(versions)}]'
        else:
            msg += " [no supported compiler versions]"
        raise UnsupportedMicroarchitecture(msg)

    @classmethod
    def from_gpu(cls, gpu: GPU) -> "GPUMicroarch":
        """Construct a GPU microarchitecture from a GPU object."""
        if not gpu.vendor:
            raise ValueError(f"Cannot construct GPUMicroarch from {gpu!r}: missing vendor")

        name: str = ""
        if gpu.vendor == "nvidia":
            if not gpu.compute_capability:
                raise ValueError(
                    f"Cannot construct GPUMicroarch from {gpu!r}: missing compute_capability"
                )
            name = gpu.compute_capability.name

        elif gpu.vendor == "amd":
            if not gpu.gfx_target:
                raise ValueError(f"Cannot construct GPUMicroarch from {gpu!r}: missing gfx_target")
            name = gpu.gfx_target.name

        # If vendor field is populated but unsupported (e.g. Intel for the time being)
        else:
            raise ValueError(
                f"Cannot construct GPUMicroarch from {gpu!r}: invalid vendor {gpu.vendor!r}"
            )

        return cls(name=name, vendor=gpu.vendor)


def _satisfies_version_constraint(constraint: str, version: str) -> bool:
    """Returns True if ``version`` falls within the ``min:max`` range in ``constraint``.

    Either bound may be empty. Version suffixes are ignored, and versions are compared as tuples
    of integers.
    """
    min_version, max_version = constraint.split(":")

    def tuplify(ver: str):
        ver, _ = version_components(ver)
        return tuple(int(y) for y in ver.split("."))

    version_tuple = tuplify(version)
    if min_version and tuplify(min_version) > version_tuple:
        return False
    if max_version and tuplify(max_version) < version_tuple:
        return False
    return True
