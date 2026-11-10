# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""Hygon production data integration; synthetic inputs except the shared M4 fixture."""
import io

import pytest

import archspec.cpu as cpu
from archspec.cpu import detect


@pytest.fixture
def linux_hygon(monkeypatch):
    monkeypatch.setattr(detect, "_machine", lambda: "x86_64")
    monkeypatch.setattr(detect.platform, "system", lambda: "Linux")
    detect.host.cache_clear()
    yield
    detect.host.cache_clear()


def detect_hygon(monkeypatch, model, features):
    text = "vendor_id : HygonGenuine\ncpu family : 24\nmodel : {}\nflags : {}\n\n".format(
        model, " ".join(sorted(features))
    )
    monkeypatch.setattr(detect, "open", lambda path: io.StringIO(text), raising=False)
    detect.host.cache_clear()
    return detect.host().name


@pytest.mark.parametrize("model", [4, 6, 7, 8])
@pytest.mark.parametrize("reverse", [False, True])
def test_production_identity_selection(monkeypatch, linux_hygon, model, reverse):
    if reverse:
        # Reverse the complete production registry, not the CPU feature flags.
        monkeypatch.setattr(detect, "TARGETS", dict(reversed(list(cpu.TARGETS.items()))))
    name = "c86_4g_m{}".format(model)
    assert detect_hygon(monkeypatch, model, cpu.TARGETS[name].features) == name


@pytest.mark.parametrize("model", [4, 6, 7, 8])
def test_mapped_target_requires_its_features(monkeypatch, linux_hygon, model):
    name = "c86_4g_m{}".format(model)
    features = cpu.TARGETS[name].features - {"clzero"}
    assert detect_hygon(monkeypatch, model, features) not in {
        "c86_4g_m4", "c86_4g_m6", "c86_4g_m7", "c86_4g_m8"
    }


@pytest.mark.parametrize("model", [4, 6, 7, 8])
@pytest.mark.parametrize(
    "compiler,version,native",
    [("gcc", "16.1.7", False), ("gcc", "16.2.0", True),
     ("clang", "23.0.9", False), ("clang", "23.1.0", True)],
)
def test_native_compiler_name_boundaries(model, compiler, version, native):
    target = cpu.TARGETS["c86_4g_m{}".format(model)]
    flags = target.optimization_flags(compiler, version)
    if native:
        name = "c86-4g-m{}".format(model)
        assert "-march=" + name in flags
        assert "-mtune=" + name in flags
    else:
        level = 3 if model in (4, 6) else 4
        assert flags == "-march=x86-64-v{} -mtune=generic".format(level)


def test_clang_m8_does_not_enable_unmodeled_shstk():
    flags = cpu.TARGETS["c86_4g_m8"].optimization_flags("clang", "23.1.0")
    assert "-mno-shstk" in flags


@pytest.mark.parametrize("model", [4, 6, 7, 8])
def test_old_gcc_patch_release_uses_explicit_fallback(model):
    flags = cpu.TARGETS["c86_4g_m{}".format(model)].optimization_flags("gcc", "11.0.1")
    assert "-march=x86-64 " in flags
    assert "-mavx2" in flags
