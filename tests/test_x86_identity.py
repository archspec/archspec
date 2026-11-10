# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""Synthetic identity preference tests; no M7/M8 hardware is required."""

import io

import jsonschema
import pytest

import archspec.cpu as cpu
from archspec.cpu import detect
from archspec.cpu.schema import TARGETS_JSON, TARGETS_JSON_SCHEMA


@pytest.fixture
def identity_targets(monkeypatch):
    # Equal ISA candidates isolate selection from hardware ISA validation.
    parent = cpu.TARGETS["x86_64_v4"]
    for name in ("c86_4g_m7", "c86_4g_m8"):
        monkeypatch.setitem(
            cpu.TARGETS,
            name,
            cpu.Microarchitecture(name, [parent], "HygonGenuine", set(parent.features), {}),
        )
    mappings = {"HygonGenuine": {"24": {"7": "c86_4g_m7", "8": "c86_4g_m8"}}}
    monkeypatch.setitem(TARGETS_JSON, "x86_cpu_targets", mappings)
    monkeypatch.setattr(detect, "_machine", lambda: "x86_64")
    monkeypatch.setattr(detect.platform, "system", lambda: "Linux")
    detect.host.cache_clear()
    yield parent, mappings
    detect.host.cache_clear()


def run_host(monkeypatch, flags, vendor="HygonGenuine", family="24", model="7"):
    text = "vendor_id : {}\ncpu family : {}\nmodel : {}\nflags : {}\n\n".format(
        vendor, family, model, " ".join(sorted(flags))
    )
    monkeypatch.setattr(detect, "open", lambda path: io.StringIO(text), raising=False)
    detect.host.cache_clear()
    return detect.host().name


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("model", ["7", "8"])
def test_identity_selects_target_independent_of_order(
    monkeypatch, identity_targets, reverse, model
):
    parent, _ = identity_targets
    names = ["c86_4g_m7", "c86_4g_m8"]
    if reverse:
        # Mutate only a replacement dict, so fixture teardown restores the original.
        targets = dict(cpu.TARGETS)
        values = [(name, targets.pop(name)) for name in names]
        targets.update(reversed(values))
        monkeypatch.setattr(detect, "TARGETS", targets)
    assert run_host(monkeypatch, parent.features, model=model) == "c86_4g_m" + model


@pytest.mark.parametrize(
    "family,model",
    [("24", "99"), ("25", "7"), ("", "7"), ("bad", "7"), ("24", ""), ("24", "bad"), ("-1", "7")],
)
def test_unknown_or_invalid_identity_keeps_original_path(
    monkeypatch, identity_targets, family, model
):
    parent, _ = identity_targets
    expected = run_host(monkeypatch, parent.features, family=family, model=model)
    monkeypatch.delitem(TARGETS_JSON, "x86_cpu_targets")
    assert run_host(monkeypatch, parent.features, family=family, model=model) == expected


def test_vendor_mismatch(monkeypatch, identity_targets):
    parent, _ = identity_targets
    assert run_host(monkeypatch, parent.features, vendor="GenuineIntel") not in (
        "c86_4g_m7",
        "c86_4g_m8",
    )


def test_masked_features_exclude_mapped_target(monkeypatch, identity_targets):
    parent, _ = identity_targets
    assert run_host(monkeypatch, parent.features - {"avx512f"}, model="8") == "x86_64_v3"


@pytest.mark.parametrize("target", ["does-not-exist", "cascadelake"])
def test_unusable_mapping_keeps_original_path(monkeypatch, identity_targets, target):
    parent, mappings = identity_targets
    mappings["HygonGenuine"]["24"]["8"] = target
    expected = run_host(monkeypatch, parent.features, model="8")
    monkeypatch.delitem(TARGETS_JSON, "x86_cpu_targets")
    assert run_host(monkeypatch, parent.features, model="8") == expected


def test_best_generic_constraint(monkeypatch, identity_targets):
    parent, mappings = identity_targets
    mappings["HygonGenuine"]["24"]["8"] = "x86_64_v2"
    assert run_host(monkeypatch, parent.features, model="8") == "c86_4g_m7"


def test_missing_identity_fields(monkeypatch, identity_targets):
    assert detect._x86_target_from_identity("HygonGenuine", None, "7") == ""
    assert detect._x86_target_from_identity("HygonGenuine", "24", None) == ""
    assert detect._x86_target_from_identity("HygonGenuine", "024", "008") == "c86_4g_m8"


def test_schema_accepts_optional_mapping(identity_targets):
    jsonschema.validate(dict(TARGETS_JSON), dict(TARGETS_JSON_SCHEMA))
    original = dict(TARGETS_JSON)
    original.pop("x86_cpu_targets")
    jsonschema.validate(original, dict(TARGETS_JSON_SCHEMA))


@pytest.mark.parametrize(
    "mapping",
    [
        {"HygonGenuine": {"0x18": {"7": "c86_4g_m7"}}},
        {"HygonGenuine": {"24": {"07": "c86_4g_m7"}}},
        {"HygonGenuine": {"24": {"7": ""}}},
        {"HygonGenuine": {"24": {"7": ["c86_4g_m7", "c86_4g_m8"]}}},
    ],
)
def test_schema_rejects_invalid_or_ambiguous_mapping(mapping):
    data = dict(TARGETS_JSON)
    data["x86_cpu_targets"] = mapping
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, dict(TARGETS_JSON_SCHEMA))


def test_extension_mapping_loads(tmp_path):
    from archspec.cpu import schema

    base = tmp_path / "base.json"
    extension = tmp_path / "extension.json"
    base.write_text('{"x86_cpu_targets": {}}')
    extension.write_text('{"x86_cpu_targets": {"HygonGenuine": {"24": {"8": "m8"}}}}')
    assert schema._load(base, extension)["x86_cpu_targets"]["HygonGenuine"]["24"]["8"] == "m8"


def test_identity_preference_overrides_ranking(monkeypatch, identity_targets):
    parent, _ = identity_targets
    # A smaller feature count is still eligible when all constraints hold.
    target = cpu.TARGETS["c86_4g_m8"]
    monkeypatch.setattr(target, "features", set(parent.features))
    monkeypatch.setattr(cpu.TARGETS["c86_4g_m7"], "features", set(parent.features) | {"clwb"})
    assert run_host(monkeypatch, set(parent.features) | {"clwb"}, model="8") == "c86_4g_m8"


def test_masked_target_specific_feature_keeps_other_candidate(monkeypatch, identity_targets):
    parent, _ = identity_targets
    target = cpu.TARGETS["c86_4g_m8"]
    monkeypatch.setattr(target, "features", set(parent.features) | {"clwb"})
    # M8 alone is ineligible; the existing path can still choose M7.
    assert run_host(monkeypatch, parent.features, model="8") == "c86_4g_m7"


def test_identity_cannot_select_another_architecture(monkeypatch, identity_targets):
    parent, mappings = identity_targets
    mappings["HygonGenuine"]["24"]["8"] = "aarch64"
    assert run_host(monkeypatch, parent.features, model="8") == "c86_4g_m7"


def test_vendor_target_below_best_generic_is_not_preferred(monkeypatch, identity_targets):
    parent, mappings = identity_targets
    legacy = cpu.Microarchitecture(
        "legacy_hygon",
        [cpu.TARGETS["x86_64_v2"]],
        "HygonGenuine",
        set(cpu.TARGETS["x86_64_v3"].features),
        {},
    )
    monkeypatch.setitem(cpu.TARGETS, legacy.name, legacy)
    mappings["HygonGenuine"]["24"]["8"] = legacy.name
    assert run_host(monkeypatch, parent.features, model="8") == "c86_4g_m7"
