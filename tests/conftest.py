# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
import pytest

import archspec.cpu.detect
import archspec.cpu.microarchitecture
import archspec.cpu.schema
from archspec.cpu.microarchitecture import _known_microarchitectures
from archspec.cpu.schema import LazyDictionary, _json_file, _load


@pytest.fixture()
def reset_global_state(monkeypatch):
    """Returns a callable that resets the global state of archspec"""

    def _func():
        monkeypatch.setattr(
            archspec.cpu.schema,
            "TARGETS_JSON",
            LazyDictionary(_load, *_json_file("microarchitectures.json", allow_custom=True)),
        )
        monkeypatch.setattr(archspec.cpu.detect, "TARGETS_JSON", archspec.cpu.schema.TARGETS_JSON)
        monkeypatch.setattr(
            archspec.cpu.schema,
            "CPUID_JSON",
            LazyDictionary(_load, *_json_file("cpuid.json", allow_custom=True)),
        )
        monkeypatch.setattr(archspec.cpu.detect, "CPUID_JSON", archspec.cpu.schema.TARGETS_JSON)
        monkeypatch.setattr(
            archspec.cpu.microarchitecture,
            "TARGETS",
            LazyDictionary(_known_microarchitectures),
        )
        monkeypatch.setattr(
            archspec.cpu.detect,
            "TARGETS",
            archspec.cpu.microarchitecture.TARGETS,
        )
        monkeypatch.setattr(
            archspec.cpu,
            "TARGETS",
            archspec.cpu.microarchitecture.TARGETS,
        )

    return _func


@pytest.fixture(autouse=True)
def clear_host_cache():
    """Clears the cache for `archspec.cpu.host()`, `archspec.cpu.detect._machine()`, and
    `archspec.cpu.detect._darwin_sysctl_data()` before each test."""
    archspec.cpu.detect.host.cache_clear()
    archspec.cpu.detect._machine.cache_clear()
    archspec.cpu.detect._darwin_sysctl_data.cache_clear()
