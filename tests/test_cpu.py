# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import contextlib
import csv
import os.path
from typing import NamedTuple

import jsonschema
import pytest

import archspec.cpu
import archspec.cpu.alias
import archspec.cpu.detect
import archspec.cpu.schema

# This is needed to check that with repr we could create equivalent objects
Microarchitecture = archspec.cpu.Microarchitecture


@pytest.fixture(
    params=[
        "linux-ubuntu18.04-broadwell",
        "linux-rhel7-broadwell",
        "linux-rhel7-skylake_avx512",
        "linux-rhel7-ivybridge",
        "linux-rhel7-haswell",
        "linux-rhel7-x86_64_v3",
        "linux-rhel7-zen",
        "linux-ubuntu20.04-zen3",
        "linux-rocky8.5-zen4",
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
        "darwin-bigsur-m1",
        "darwin-monterey-m1",
        "bgq-rhel6-power7",
        "linux-amazon-cortex_a72",
        "linux-amazon-neoverse_n1",
        "linux-amazon-neoverse_v1",
        "linux-sifive-u74mc",
        "linux-asahi-m1",
        "linux-asahi-m2",
        "darwin-monterey-m2",
        "linux-rocky8-a64fx",
        "linux-amazon2-sapphirerapids",
        "linux-unknown-sapphirerapids",
        "linux-rhel8-power9",
        "linux-unknown-power10",
        "linux-ubuntu22.04-neoverse_v2",
        "linux-rhel9-neoverse_v2",
        "windows-cpuid-broadwell",
        "windows-cpuid-icelake",
        "linux-rhel8-neoverse_v1",
        "linux-unknown-neoverse_v2",
        "linux-rhel9-neoverse_n2",
        "linux-ubuntu22.04-neoverse_n2",
        "linux-rocky9-zen5",
    ]
)
def expected_target(request, monkeypatch):
    cpu = archspec.cpu
    platform, operating_system, target = request.param.split("-")

    # This is the default to use for tests on Darwin, since it will match
    # Intel based MacBook, and will be the worst case scenario for Apple M1
    # (i.e. Python for x86_64 running on top of Rosetta)
    architecture_family = "x86_64" if platform == "darwin" else archspec.cpu.TARGETS[target].family
    if platform == "windows":
        architecture_family = "AMD64" if architecture_family == "x86_64" else "ARM64"

    monkeypatch.setattr(cpu.detect.platform, "machine", lambda: str(architecture_family))

    target_dir = targets_directory()
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
        monkeypatch.setattr(cpu.detect, "_check_output", mock_check_output(filename))

    elif platform == "windows":
        monkeypatch.setattr(cpu.detect.platform, "system", lambda: "Windows")
        filename = os.path.join(target_dir, request.param)
        monkeypatch.setattr(cpu.detect, "CPUID", mock_CpuidInfoCollector(filename))

    return archspec.cpu.TARGETS[target]


def targets_directory():
    test_dir = os.path.dirname(__file__)
    target_dir = os.path.join(test_dir, "..", "archspec", "json", "tests", "targets")
    return target_dir


@pytest.fixture(
    params=[
        ("darwin-mojave-ivybridge", "Intel(R) Core(TM) i5-3230M CPU @ 2.60GHz"),
        ("darwin-mojave-haswell", "Intel(R) Core(TM) i7-4980HQ CPU @ 2.80GHz"),
        ("darwin-mojave-skylake", "Intel(R) Core(TM) i7-6700K CPU @ 4.00GHz"),
        ("darwin-monterey-m1", "Apple M1 Pro"),
        ("darwin-monterey-m2", "Apple M2"),
        ("windows-cpuid-broadwell", "Intel(R) Core(TM) i7-5500U CPU @ 2.40GHz"),
        ("windows-cpuid-icelake", "11th Gen Intel(R) Core(TM) i7-1185G7 @ 3.00GHz"),
    ]
)
def expected_brand_string(request, monkeypatch):
    test_file, expected_result = request.param
    filename = os.path.join(targets_directory(), test_file)
    if "darwin" in test_file:
        monkeypatch.setattr(archspec.cpu.detect.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(archspec.cpu.detect, "_check_output", mock_check_output(filename))
    elif "cpuid" in test_file:
        monkeypatch.setattr(archspec.cpu.detect, "host", lambda: archspec.cpu.TARGETS["x86_64"])
        monkeypatch.setattr(archspec.cpu.detect.platform, "system", lambda: "Windows")
        monkeypatch.setattr(archspec.cpu.detect, "CPUID", mock_CpuidInfoCollector(filename))
    return expected_result


def mock_check_output(filename):
    info = {}
    with open(filename) as f:
        for line in f:
            key, value = line.split(":")
            info[key.strip()] = value.strip()

    def _check_output(args, env):
        current_key = args[-1]
        return info[current_key]

    return _check_output


def mock_CpuidInfoCollector(filename):
    class MockRegisters(NamedTuple):
        eax: int
        ebx: int
        ecx: int
        edx: int

    class MockCPUID:
        def __init__(self):
            self.data = {}
            with open(filename) as f:
                reader = csv.reader(f)
                for row in reader:
                    key = int(row[0]), int(row[1])
                    values = tuple(int(x) for x in row[2:])
                    self.data[key] = MockRegisters(*values)

        def registers_for(self, eax, ecx):
            return self.data.get((eax, ecx), MockRegisters(0, 0, 0, 0))

    return MockCPUID


@pytest.fixture(params=[x for x in archspec.cpu.TARGETS])
def supported_target(request):
    return request.param


@pytest.fixture()
def extension_file(tmp_path):
    extension_file = tmp_path / "microarchitectures.json"
    extension_file.write_text(
        """
{
  "microarchitectures": {
    "pentium2.5": {
      "from": ["pentium2"],
      "vendor": "BogusIntel",
      "features": [
        "mmx",
        "mehmehx"
      ]
    }
  }
}
"""
    )
    return extension_file


def test_target_detection(expected_target):
    detected_target = archspec.cpu.host()
    assert detected_target == expected_target, f"{detected_target} == {expected_target}"


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
        # Test ordering with x86_64 virtual versions
        ("x86_64 < x86_64_v2", True),
        ("x86_64_v4 < x86_64_v2", False),
        ("core2 > x86_64_v2", False),
        ("nehalem > x86_64_v2", True),
        ("bulldozer > x86_64_v2", True),
        ("excavator > x86_64_v2", True),
        ("excavator > x86_64_v3", True),
        ("zen > x86_64_v3", True),
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
    [
        ("skylake", "x86_64"),
        ("zen", "x86_64"),
        ("pentium2", "x86"),
        ("excavator", "x86_64"),
    ],
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


@pytest.mark.parametrize(
    "json_data,schema",
    [
        (archspec.cpu.schema.TARGETS_JSON.data, archspec.cpu.schema.TARGETS_JSON_SCHEMA.data),
        (archspec.cpu.schema.CPUID_JSON.data, archspec.cpu.schema.CPUID_JSON_SCHEMA.data),
    ],
)
def test_validate_json_files(json_data, schema):
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
        ("neoverse_v1", "gcc", "12.1.0", "-mcpu=neoverse-v1"),
        # Test Apple's Clang
        ("x86_64", "apple-clang", "11.0.0", "-march=x86-64"),
        (
            "icelake",
            "apple-clang",
            "11.0.0",
            "-march=icelake-client -mtune=icelake-client",
        ),
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
        # Test AMD aocc
        ("zen2", "aocc", "2.2", "-march=znver2 -mtune=znver2"),
        # Test that an unknown compiler returns an empty string
        ("sandybridge", "unknown", "4.8.5", ""),
        # Test ARM compiler support
        ("a64fx", "arm", "21.0", "-march=armv8.2-a+crc+crypto+fp16+sve"),
        # Test NVHPC compiler support
        ("icelake", "nvhpc", "23", "-tp skylake"),
        ("bulldozer", "nvhpc", "23", "-tp bulldozer"),
        ("neoverse_n1", "nvhpc", "23", "-tp neoverse-n1"),
        ("power8le", "nvhpc", "23", "-tp pwr8"),
    ],
)
def test_optimization_flags(target_name, compiler, version, expected_flags):
    target = archspec.cpu.TARGETS[target_name]
    flags = target.optimization_flags(compiler, version)
    assert flags == expected_flags


@pytest.mark.parametrize(
    "target_name,compiler,version",
    [
        ("excavator", "gcc", "4.8.5"),
        ("broadwell", "apple-clang", "7.0.0"),
        ("x86_64", "nvhpc", "23"),
        ("x86_64_v2", "nvhpc", "23"),
        ("ppc64le", "nvhpc", "23"),
    ],
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
    schema = archspec.cpu.schema.TARGETS_JSON_SCHEMA
    fa_schema = schema["properties"]["feature_aliases"]
    aliases_in_schema = set(fa_schema["patternProperties"]["([\\w]*)"]["properties"])
    aliases_implemented = set(archspec.cpu.alias._FEATURE_ALIAS_PREDICATE)
    assert aliases_implemented == aliases_in_schema


@pytest.mark.parametrize(
    "target,expected",
    [
        ("haswell", "x86_64_v3"),
        ("bulldozer", "x86_64_v2"),
        ("zen2", "x86_64_v3"),
        ("icelake", "x86_64_v4"),
        # Check that a generic level returns itself
        ("x86_64_v3", "x86_64_v3"),
    ],
)
def test_generic_property(target, expected):
    t = archspec.cpu.TARGETS[target]
    assert str(t.generic) == expected


def test_versions_are_ranges(supported_target):
    """Tests that all the compiler versions in the JSON file are ranges, containing an
    explicit ':' character.
    """
    target_under_test = archspec.cpu.TARGETS[supported_target]
    for compiler_name, entries in target_under_test.compilers.items():
        for compiler_info in entries:
            assert ":" in compiler_info["versions"]


def test_round_trip_dict():
    for name in archspec.cpu.TARGETS:
        uarch_copy = Microarchitecture.from_dict(archspec.cpu.TARGETS[name].to_dict())
        assert uarch_copy == archspec.cpu.TARGETS[name]


def test_microarchitectures_extension(extension_file, monkeypatch, reset_global_state):
    """Tests that we can update the JSON file using a user defined extension"""
    monkeypatch.setenv("ARCHSPEC_EXTENSION_CPU_DIR", str(extension_file.parent))
    reset_global_state()
    assert "pentium2.5" in archspec.cpu.TARGETS
    assert "mehmehx" in archspec.cpu.TARGETS["pentium2.5"]
    assert archspec.cpu.TARGETS["pentium2.5"].vendor == "BogusIntel"
    assert archspec.cpu.TARGETS["pentium2"] < archspec.cpu.TARGETS["pentium2.5"]


def test_only_one_extension_file(extension_file, monkeypatch, reset_global_state):
    """Tests that we can supply only one extension file in a custom directory, and that reading
    any other JSON file will not give errors.
    """
    monkeypatch.setenv("ARCHSPEC_EXTENSION_CPU_DIR", str(extension_file.parent))
    reset_global_state()
    assert "pentium2.5" in archspec.cpu.TARGETS
    assert "flags" in archspec.cpu.schema.CPUID_JSON


def test_brand_string(expected_brand_string):
    assert archspec.cpu.detect.brand_string() == expected_brand_string


@pytest.mark.parametrize(
    "version_str",
    [
        "13.2.0.debug",
        "optimized",
    ],
)
def test_error_message_unknown_compiler_version(version_str):
    """Tests that passing a version to Microarchitecture.optimization_flags with a wrong format,
    raises a comprehensible error message.
    """
    t = archspec.cpu.TARGETS["icelake"]
    with pytest.raises(
        archspec.cpu.InvalidCompilerVersion,
        match="invalid format for the compiler version argument",
    ):
        t.optimization_flags("gcc", version_str)


@pytest.mark.parametrize(
    "names,expected_length",
    [(("icelake", "broadwell"), 2), (("icelake", "broadwell", "icelake"), 2)],
)
def test_targets_can_be_used_in_sets(names, expected_length):
    s = {archspec.cpu.TARGETS[name] for name in names}
    assert len(s) == expected_length
