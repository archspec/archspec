# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import pytest

import contextlib
import os.path

import jsonschema

import archspec.cpu
import archspec.cpu.alias
import archspec.cpu.detect
import archspec.cpu.schema

# This is needed to check that with repr we could create equivalent objects
from archspec.cpu import Microarchitecture


@pytest.fixture(
    params=[
        "linux-ubuntu18.04-broadwell",
        "linux-rhel7-broadwell",
        "linux-rhel7-skylake_avx512",
        "linux-rhel7-ivybridge",
        "linux-rhel7-haswell",
        "linux-rhel7-zen",
        "linux-scientific7-k10",
        "linux-scientificfermi6-bulldozer",
        "linux-scientificfermi6-piledriver",
        "linux-scientific7-piledriver",
        "linux-rhel6-piledriver",
        "linux-centos7-power8le",
        "linux-centos7-thunderx2",
        "linux-centos7-cascadelake",
        "darwin-mojave-ivybridge",
        "darwin-mojave-haswell",
        "darwin-mojave-skylake",
        "bgq-rhel6-power7",
        "linux-amazon-graviton",
        "linux-amazon-graviton2",
    ]
)
def expected_target(request, monkeypatch):
    cpu = archspec.cpu
    platform, operating_system, target = request.param.split("-")

    architecture_family = archspec.cpu.TARGETS[target].family
    monkeypatch.setattr(
        cpu.detect.platform, "machine", lambda: str(architecture_family)
    )

    test_dir = os.path.dirname(__file__)
    target_dir = os.path.join(test_dir, "..", "archspec", "json", "tests", "targets")
    # Monkeypatch for linux
    if platform in ("linux", "bgq"):
        monkeypatch.setattr(cpu.detect.platform, "system", lambda: "Linux")

        @contextlib.contextmanager
        def _open(not_used_arg):
            filename = os.path.join(target_dir, request.param)
            with open(filename) as f:
                yield f

        monkeypatch.setattr(cpu.detect, "open", _open, raising=False)

    elif platform == "darwin":
        monkeypatch.setattr(cpu.detect.platform, "system", lambda: "Darwin")

        filename = os.path.join(target_dir, request.param)
        info = {}
        with open(filename) as f:
            for line in f:
                key, value = line.split(":")
                info[key.strip()] = value.strip()

        def _check_output(args, env):
            current_key = args[-1]
            return info[current_key]

        monkeypatch.setattr(cpu.detect, "_check_output", _check_output)

    return archspec.cpu.TARGETS[target]


@pytest.fixture(params=[x for x in archspec.cpu.TARGETS])
def supported_target(request):
    return request.param


def test_target_detection(expected_target):
    detected_target = archspec.cpu.host()
    assert detected_target == expected_target


def test_no_dashes_in_target_names(supported_target):
    assert "-" not in supported_target


def test_str_conversion(supported_target):
    assert supported_target == str(archspec.cpu.TARGETS[supported_target])


def test_repr_conversion(supported_target):
    target = archspec.cpu.TARGETS[supported_target]
    assert eval(repr(target)) == target


def test_equality(supported_target):
    target = archspec.cpu.TARGETS[supported_target]

    for name, other_target in archspec.cpu.TARGETS.items():
        if name == supported_target:
            assert other_target == target
        else:
            assert other_target != target


@pytest.mark.parametrize(
    "operation,expected_result",
    [
        # Test microarchitectures that are ordered with respect to each other
        ("x86_64 < skylake", True),
        ("icelake > skylake", True),
        ("piledriver <= steamroller", True),
        ("zen2 >= zen", True),
        ("zen >= zen", True),
        ("aarch64 <= thunderx2", True),
        ("aarch64 <= a64fx", True),
        # Test unrelated microarchitectures
        ("power8 < skylake", False),
        ("power8 <= skylake", False),
        ("skylake < power8", False),
        ("skylake <= power8", False),
        # Test microarchitectures of the same family that are not a "subset"
        # of each other
        ("cascadelake > cannonlake", False),
        ("cascadelake < cannonlake", False),
        ("cascadelake <= cannonlake", False),
        ("cascadelake >= cannonlake", False),
        ("cascadelake == cannonlake", False),
        ("cascadelake != cannonlake", True),
    ],
)
def test_partial_ordering(operation, expected_result):
    target, operator, other_target = operation.split()
    target = archspec.cpu.TARGETS[target]
    other_target = archspec.cpu.TARGETS[other_target]
    code = "target " + operator + "other_target"
    assert eval(code) is expected_result


@pytest.mark.parametrize(
    "target_name,expected_family",
    [("skylake", "x86_64"), ("zen", "x86_64"), ("pentium2", "x86")],
)
def test_architecture_family(target_name, expected_family):
    target = archspec.cpu.TARGETS[target_name]
    assert str(target.family) == expected_family


@pytest.mark.parametrize(
    "target_name,feature",
    [
        ("skylake", "avx2"),
        ("icelake", "avx512f"),
        # Test feature aliases
        ("icelake", "avx512"),
        ("skylake", "sse3"),
        ("power8", "altivec"),
        ("broadwell", "sse4.1"),
        ("skylake", "clflushopt"),
        ("aarch64", "neon"),
    ],
)
def test_features_query(target_name, feature):
    target = archspec.cpu.TARGETS[target_name]
    assert feature in target


@pytest.mark.parametrize(
    "target_name,wrong_feature",
    [("skylake", 1), ("bulldozer", archspec.cpu.TARGETS["x86_64"])],
)
def test_wrong_types_for_features_query(target_name, wrong_feature):
    target = archspec.cpu.TARGETS[target_name]
    with pytest.raises(TypeError, match="only objects of string types"):
        assert wrong_feature in target


def test_generic_microarchitecture():
    generic_march = archspec.cpu.generic_microarchitecture("foo")

    assert generic_march.name == "foo"
    assert not generic_march.features
    assert not generic_march.ancestors
    assert generic_march.vendor == "generic"


def test_target_json_schema():
    # The file microarchitectures.json contains static data i.e. data that is
    # not meant to be modified by users directly. It is thus sufficient to
    # validate it only once during unit tests.
    json_data = archspec.cpu.schema.TARGETS_JSON.data
    schema = archspec.cpu.schema.SCHEMA.data
    jsonschema.validate(json_data, schema)


@pytest.mark.parametrize(
    "target_name,compiler,version,expected_flags",
    [
        # Test GCC
        ("x86_64", "gcc", "4.9.3", "-march=x86-64 -mtune=generic"),
        ("x86_64", "gcc", "4.2.0", "-march=x86-64 -mtune=generic"),
        ("x86_64", "gcc", "4.1.1", "-march=x86-64 -mtune=x86-64"),
        ("nocona", "gcc", "4.9.3", "-march=nocona -mtune=nocona"),
        ("nehalem", "gcc", "4.9.3", "-march=nehalem -mtune=nehalem"),
        ("nehalem", "gcc", "4.8.5", "-march=corei7 -mtune=corei7"),
        ("sandybridge", "gcc", "4.8.5", "-march=corei7-avx -mtune=corei7-avx"),
        ("thunderx2", "gcc", "4.8.5", "-march=armv8-a"),
        ("thunderx2", "gcc", "4.9.3", "-march=armv8-a+crc+crypto"),
        # Test Apple's Clang
        ("x86_64", "apple-clang", "11.0.0", "-march=x86-64"),
        # Test Clang / LLVM
        ("sandybridge", "clang", "3.9.0", "-march=sandybridge -mtune=sandybridge"),
        ("icelake", "clang", "6.0.0", "-march=icelake -mtune=icelake"),
        ("icelake", "clang", "8.0.0", "-march=icelake-client -mtune=icelake-client"),
        ("zen2", "clang", "9.0.0", "-march=znver2 -mtune=znver2"),
        ("power9le", "clang", "8.0.0", "-mcpu=power9 -mtune=power9"),
        ("thunderx2", "clang", "6.0.0", "-mcpu=thunderx2t99"),
        # Test Intel on Intel CPUs
        ("sandybridge", "intel", "17.0.2", "-march=corei7-avx -mtune=corei7-avx"),
        ("sandybridge", "intel", "18.0.5", "-march=sandybridge -mtune=sandybridge"),
        # Test Intel on AMD CPUs
        pytest.param(
            "steamroller",
            "intel",
            "17.0.2",
            "-msse4.2",
            marks=pytest.mark.filterwarnings("ignore::UserWarning"),
        ),
        pytest.param(
            "zen",
            "intel",
            "17.0.2",
            "-march=core-avx2 -mtune=core-avx2",
            marks=pytest.mark.filterwarnings("ignore::UserWarning"),
        ),
        # Test that an unknown compiler returns an empty string
        ("sandybridge", "unknown", "4.8.5", ""),
    ],
)
def test_optimization_flags(target_name, compiler, version, expected_flags):
    target = archspec.cpu.TARGETS[target_name]
    flags = target.optimization_flags(compiler, version)
    assert flags == expected_flags


@pytest.mark.parametrize(
    "target_name,compiler,version",
    [("excavator", "gcc", "4.8.5"), ("broadwell", "apple-clang", "11.0.0")],
)
def test_unsupported_optimization_flags(target_name, compiler, version):
    target = archspec.cpu.TARGETS[target_name]
    with pytest.raises(archspec.cpu.UnsupportedMicroarchitecture):
        target.optimization_flags(compiler, version)


@pytest.mark.parametrize(
    "operation,expected_result",
    [
        # In the tests below we won't convert the right hand side to
        # Microarchitecture, so that automatic conversion from a known
        # target name will be tested
        ("cascadelake > cannonlake", False),
        ("cascadelake < cannonlake", False),
        ("cascadelake <= cannonlake", False),
        ("cascadelake >= cannonlake", False),
        ("cascadelake == cannonlake", False),
        ("cascadelake != cannonlake", True),
    ],
)
def test_automatic_conversion_on_comparisons(operation, expected_result):
    target, operator, other_target = operation.split()
    target = archspec.cpu.TARGETS[target]
    code = "target " + operator + "other_target"
    assert eval(code) is expected_result


@pytest.mark.parametrize(
    "version,expected_number,expected_suffix",
    [
        ("4.2.0", "4.2.0", ""),
        ("4.2.0-apple", "4.2.0", "apple"),
        ("my-funny-name-with-dashes", "", "my-funny-name-with-dashes"),
        ("10.3.56~svnr64537", "10.3.56", "~svnr64537"),
    ],
)
def test_version_components(version, expected_number, expected_suffix):
    number, suffix = archspec.cpu.version_components(version)
    assert number == expected_number
    assert suffix == expected_suffix


def test_all_alias_predicates_are_implemented():
    schema = archspec.cpu.schema.SCHEMA
    fa_schema = schema["properties"]["feature_aliases"]
    aliases_in_schema = set(fa_schema["patternProperties"]["([\\w]*)"]["properties"])
    aliases_implemented = set(archspec.cpu.alias._FEATURE_ALIAS_PREDICATE)
    assert aliases_implemented == aliases_in_schema
