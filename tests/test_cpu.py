# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import contextlib
import csv
import itertools
import os.path
from io import StringIO
from typing import NamedTuple

import jsonschema
import pytest

import archspec.cpu
import archspec.cpu.alias
import archspec.cpu.detect
import archspec.cpu.schema
from archspec.cpu import (
    ArchspecError,
    InvalidRange,
    Microarchitecture,
    MicroarchitectureRange,
    MicroarchitectureRangeList,
    UnknownMicroarchitecture,
)


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
        "darwin-sequoia-m3",
        "darwin-sequoia-m4",
        "linux-spacemit-x60",
        "linux-debian13-x60",
        "linux-ubuntu22.04-ampere1",
        "linux-ubuntu22.04-ampere1a",
        "linux-ubuntu24.04-alderlake",
        "linux-ubuntu26.04-arrowlake_s",
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
            key, sep, value = line.partition(":")
            if sep:
                info[key.strip()] = value.strip()

    def _check_output(args, env):
        keys = [k for k in args[1:] if not k.startswith("-")]
        if "-n" in args:
            return "\n".join(info.get(key, "") for key in keys)
        return "\n".join(f"{key}: {info[key]}" for key in keys if key in info)

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
    assert f"Microarchitecture({supported_target!r})" == repr(target)


def test_tree(supported_target):
    buffer = StringIO()
    target = archspec.cpu.TARGETS[supported_target]
    target.tree(buffer, indent=2)
    tree_lines = buffer.getvalue().splitlines()
    assert tree_lines[0].startswith(supported_target)
    for parent in target.parents:
        assert any(line.startswith(f"  {parent.name}") for line in tree_lines)


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


def test_partial_order_from_powerset_of_features():
    # If A is the set of CPU features, then the powerset P(A) is the set of all microarchitectures.
    # We define the usual partial order on P(A) as X <= Y if X is a subset of Y. Here we verify
    # that this partial order is respected by the microarchitectures.
    for child in archspec.cpu.TARGETS.values():
        for parent in child.parents:
            assert parent <= child
            assert parent.features.issubset(child.features)


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
    "brand_string,expected_name",
    [
        ("Apple processor", "m1"),
        ("Apple M1 Pro", "m1"),
        ("Apple M2 Max", "m2"),
        ("Apple M4", "m4"),
        # NOTE: this must be updated when jsonschema adds M5 and newer
        ("Apple M2000", "m4"),
    ],
)
def test_sysctl_info_apple(brand_string, expected_name):
    uarch = archspec.cpu.detect._sysctl_info_apple(
        {archspec.cpu.detect.MACHDEP_CPU_BRAND_STRING: brand_string}
    )
    assert uarch.name == expected_name
    assert uarch.vendor == "Apple"


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


def test_tree_no_duplicate_nodes():
    """In a DAG with shared ancestors (diamond pattern), each node must appear
    exactly once in tree() output.

    This test catches the bug where the ``seen`` set inside ``tree()`` is declared
    but never updated, causing shared ancestors to be printed multiple times.

    Diamond structure used:

         diamond
        /       \
      left      right
        \       /
          root
    """
    root = Microarchitecture("root", parents=[], vendor="generic", features=set(), compilers={})
    left = Microarchitecture(
        "left", parents=[root], vendor="generic", features=set(), compilers={}
    )
    right = Microarchitecture(
        "right", parents=[root], vendor="generic", features=set(), compilers={}
    )
    diamond = Microarchitecture(
        "diamond", parents=[left, right], vendor="generic", features=set(), compilers={}
    )

    buf = StringIO()
    diamond.tree(buf)
    node_names = [line.strip() for line in buf.getvalue().splitlines()]

    assert node_names.count("root") == 1, (
        f"'root' appears {node_names.count('root')} time(s); "
        "shared ancestors must appear exactly once in tree() output"
    )


def test_why_not_unknown_target():
    """Tests that why_not returns exactly the expected message for an unknown target name."""
    result = archspec.cpu.detect.why_not("not_a_real_target_xyz")
    assert result == archspec.cpu.detect._WHY_NOT_UNKNOWN.format(name="not_a_real_target_xyz")


def test_why_not_is_the_host(monkeypatch):
    """Tests that why_not returns exactly the expected message when the queried target
    is in fact the detected host.
    """
    monkeypatch.setattr(archspec.cpu.detect, "host", lambda: archspec.cpu.TARGETS["broadwell"])
    result = archspec.cpu.detect.why_not("broadwell")
    assert result == archspec.cpu.detect._WHY_NOT_IS_HOST.format(name="broadwell")


def test_why_not_host_is_more_specific(monkeypatch):
    """Tests that when the queried target is an ancestor of the host (target < host),
    the explanation is exactly the expected message naming the more specific detected host.
    """
    # haswell is a parent of broadwell, so haswell < broadwell
    monkeypatch.setattr(archspec.cpu.detect, "host", lambda: archspec.cpu.TARGETS["broadwell"])
    result = archspec.cpu.detect.why_not("haswell")
    assert result == archspec.cpu.detect._WHY_NOT_HOST_MORE_SPECIFIC.format(
        name="haswell", host="broadwell"
    )


def test_why_not_missing_features(monkeypatch):
    """Tests that for an x86_64 target that requires features the host lacks, the explanation
    names the missing features.
    """
    # Simulate a host with only broadwell-level features (no avx512)
    broadwell_info = archspec.cpu.detect.partial_uarch(
        vendor="GenuineIntel",
        features=set(archspec.cpu.TARGETS["broadwell"].features),
    )
    monkeypatch.setattr(archspec.cpu.detect, "host", lambda: archspec.cpu.TARGETS["broadwell"])
    monkeypatch.setattr(archspec.cpu.detect, "detected_info", lambda: broadwell_info)
    monkeypatch.setattr(archspec.cpu.detect, "_machine", lambda: "x86_64")

    missing = archspec.cpu.TARGETS["skylake_avx512"].features - broadwell_info.features
    result = archspec.cpu.detect.why_not("skylake_avx512")
    assert result == archspec.cpu.detect._WHY_NOT_MISSING_FEATURES.format(
        name="skylake_avx512", features=", ".join(sorted(missing))
    )


def test_why_not_wrong_family(monkeypatch):
    """Tests that when the queried target belongs to a different architecture family,
    the explanation mentions the family or architecture mismatch.
    """
    monkeypatch.setattr(archspec.cpu.detect, "host", lambda: archspec.cpu.TARGETS["broadwell"])
    monkeypatch.setattr(archspec.cpu.detect, "_machine", lambda: "x86_64")

    result = archspec.cpu.detect.why_not("power8")
    assert result == archspec.cpu.detect._WHY_NOT_WRONG_FAMILY.format(
        name="power8",
        target_family=str(archspec.cpu.TARGETS["power8"].family),
        host_family="x86_64",
    )


class TestMicroarchitectureRanges:
    @pytest.mark.parametrize(
        "lo,hi",
        [
            # lo > hi
            ("icelake", "broadwell"),
            # Different families
            ("x86_64", "neoverse_n1"),
            # Not comparable
            ("broadwell", "zen4"),
        ],
    )
    def test_errors_in_construction(self, lo, hi):
        """Tests that constructing a range with inconsistent boundaries raises InvalidRange."""
        lo, hi = archspec.cpu.TARGETS[lo], archspec.cpu.TARGETS[hi]
        with pytest.raises(InvalidRange, match="is not compatible with"):
            MicroarchitectureRange(lo=lo, hi=hi)

    @pytest.mark.parametrize(
        "lo,hi,item,expected",
        [
            # The key is one of the boundaries
            ("broadwell", "skylake", "broadwell", True),
            ("broadwell", None, "broadwell", True),
            ("broadwell", "skylake", "skylake", True),
            (None, "skylake", "skylake", True),
            # Key is in the middle of the boundary
            ("x86_64_v2", "skylake", "broadwell", True),
            ("x86_64_v2", None, "broadwell", True),
            (None, "skylake", "broadwell", True),
            # Key is not in the range
            ("broadwell", "skylake", "bulldozer", False),
            ("broadwell", None, "bulldozer", False),
            (None, "skylake", "bulldozer", False),
            # Bifurcations in the microarchitectures DAG
            ("broadwell", "cascadelake", "cannonlake", False),
            ("broadwell", "cannonlake", "cascadelake", False),
        ],
    )
    def test_range_contains(self, lo, hi, item, expected):
        """Tests that a range holds exactly the microarchitectures between its boundaries."""
        uarch_range = archspec.cpu.microarchitecture_range(lo=lo, hi=hi)
        assert (item in uarch_range) is expected
        assert (Microarchitecture.from_string(item) in uarch_range) is expected

    @pytest.mark.parametrize(
        "r1_args,r2_args,expected",
        [
            # A closed range inside an open one
            (("broadwell", "icelake"), ("x86_64_v2", None), True),
            # A closed range inside a wider closed one
            (("broadwell", "skylake"), ("x86_64", "icelake"), True),
            # Same boundaries, so each contains the other
            (("broadwell", "skylake"), ("broadwell", "skylake"), True),
            # An open range is never inside a closed one, even when they enumerate the same
            # microarchitectures today
            (("mic_knl", None), ("mic_knl", "mic_knl"), False),
            # Nested open ranges
            (("zen4", None), ("x86_64_v2", None), True),
            (("x86_64_v2", None), ("zen4", None), False),
            # Ranges from different families are never contained in one another
            (("broadwell", "skylake"), ("aarch64", None), False),
        ],
    )
    def test_range_containment(self, r1_args, r2_args, expected):
        """Tests that the comparison operators between ranges implement subset semantics."""
        r1 = archspec.cpu.microarchitecture_range(lo=r1_args[0], hi=r1_args[1])
        r2 = archspec.cpu.microarchitecture_range(lo=r2_args[0], hi=r2_args[1])

        assert (r1 <= r2) is expected
        assert (r2 >= r1) is expected
        # The strict operators agree, except when the two ranges are equal
        assert (r1 < r2) is (expected and r1 != r2)
        assert (r2 > r1) is (expected and r1 != r2)

    def test_empty_range_is_contained_in_every_range(self):
        """Tests that the empty range is a subset of any range, and contains only itself."""
        empty_range = archspec.cpu.microarchitecture_range()
        other = archspec.cpu.microarchitecture_range(lo="broadwell", hi="icelake")

        assert empty_range <= other
        assert empty_range <= empty_range
        assert not other <= empty_range
        assert empty_range.empty is True
        assert empty_range.family is None

    @pytest.mark.parametrize(
        "r1_args,r2_args",
        [
            # Overlapping, but neither is inside the other
            (("broadwell", "icelake"), ("x86_64", "skylake")),
            # Disjoint branches of the same bifurcation
            (("cannonlake", None), ("cascadelake", None)),
        ],
    )
    def test_containment_of_incomparable_ranges(self, r1_args, r2_args):
        """Tests that containment is a partial order, so two ranges can be incomparable."""
        r1 = archspec.cpu.microarchitecture_range(lo=r1_args[0], hi=r1_args[1])
        r2 = archspec.cpu.microarchitecture_range(lo=r2_args[0], hi=r2_args[1])

        assert not r1 <= r2
        assert not r2 <= r1
        assert r1 != r2

    @pytest.mark.parametrize(
        "range_str,expected_str",
        [
            # Closed ranges
            ("broadwell:skylake", "broadwell:skylake"),
            ("  broadwell : skylake  ", "broadwell:skylake"),
            # Ranges that are unbounded above
            ("broadwell:", "broadwell:"),
            # A missing lower boundary is normalized to the family of the upper one
            (":skylake", "x86_64:skylake"),
            (":neoverse_n1", "aarch64:neoverse_n1"),
            # A bare name is the range holding that microarchitecture only, and is rendered
            # back as a bare name
            ("broadwell", "broadwell"),
            ("broadwell:broadwell", "broadwell"),
            # The empty range
            ("{}", "{}"),
            (":", "{}"),
        ],
    )
    def test_range_from_string(self, range_str, expected_str):
        """Tests that a range can be parsed from its string representation, and that a missing
        lower boundary is normalized to the family of the upper one.
        """
        assert str(MicroarchitectureRange.from_string(range_str)) == expected_str

    @pytest.mark.parametrize(
        "range_str,exception",
        [
            # Too many boundaries
            ("broadwell:skylake:icelake", InvalidRange),
            # Unknown microarchitecture names
            ("broadwell:not_a_target", ValueError),
            ("not_a_target:", ValueError),
            ("not_a_target", ValueError),
            # Reversed boundaries
            ("skylake:broadwell", InvalidRange),
            # Boundaries from different families
            ("x86_64:neoverse_n1", InvalidRange),
        ],
    )
    def test_range_from_string_errors(self, range_str, exception):
        """Tests that parsing an invalid range from a string raises."""
        with pytest.raises(exception):
            MicroarchitectureRange.from_string(range_str)

    def test_iteration_is_deterministic_and_topological(self):
        """Tests that iterating a range yields a stable order, with ancestors always coming
        before their descendants.
        """
        uarch_range = archspec.cpu.microarchitecture_range(lo="x86_64_v2", hi="haswell")
        result = list(uarch_range)

        assert result == list(uarch_range), "iteration order is not stable"
        assert len(result) == len(uarch_range)
        for index, uarch in enumerate(result):
            descendants_before = [x for x in result[:index] if uarch < x]
            assert not descendants_before, f"{uarch} comes after its descendants"

    @pytest.mark.parametrize("item", [42, None, 3.14])
    def test_contains_rejects_invalid_types(self, item):
        """Tests that testing membership of an object that is not a microarchitecture, nor a
        string, raises a TypeError.
        """
        uarch_range = archspec.cpu.microarchitecture_range(lo="broadwell", hi="icelake")
        with pytest.raises(TypeError, match="only objects of string or Microarchitecture types"):
            item in uarch_range  # pylint: disable=pointless-statement

    @pytest.fixture(scope="class")
    def all_ranges(self):
        """Every valid range that can be built out of the known microarchitectures."""
        names = sorted(archspec.cpu.TARGETS)
        result = [MicroarchitectureRange()]
        for name in names:
            uarch = archspec.cpu.TARGETS[name]
            result.append(MicroarchitectureRange(lo=uarch))
            result.append(MicroarchitectureRange(hi=uarch))
        for lo_name, hi_name in itertools.combinations(names, 2):
            lo, hi = archspec.cpu.TARGETS[lo_name], archspec.cpu.TARGETS[hi_name]
            if lo <= hi:
                result.append(MicroarchitectureRange(lo=lo, hi=hi))
        return result

    @pytest.fixture(scope="class")
    def sample_ranges(self):
        """A smaller selection of ranges, covering the interesting parts of both the x86_64 and
        the aarch64 DAGs, for the properties that need to compare ranges pairwise.
        """
        names = [
            # x86_64, which is a lattice, including both sides of a bifurcation
            "x86_64",
            "x86_64_v2",
            "x86_64_v4",
            "broadwell",
            "mic_knl",
            "skylake",
            "cascadelake",
            "cannonlake",
            "icelake",
            "zen4",
            # aarch64, which is not a lattice
            "aarch64",
            "armv8.2a",
            "armv8.6a",
            "cortex_a72",
            "neoverse_n1",
            "ampere1",
            "ampere1a",
        ]
        result = [MicroarchitectureRange()]
        for name in names:
            uarch = archspec.cpu.TARGETS[name]
            result.append(MicroarchitectureRange(lo=uarch))
            result.append(MicroarchitectureRange(hi=uarch))
        return result

    def test_contains_agrees_with_the_partial_order(self, all_ranges):
        """Tests that membership in a range agrees with the partial order on its boundaries, for
        every range and every known microarchitecture.
        """
        for uarch_range in all_ranges:
            for uarch in archspec.cpu.TARGETS.values():
                if uarch_range.empty:
                    expected = False
                else:
                    expected = uarch_range.lo <= uarch and (
                        uarch_range.hi is None or uarch <= uarch_range.hi
                    )
                assert (uarch in uarch_range) is expected

    def test_range_equality_agrees_with_hashing(self, all_ranges):
        """Tests that equal ranges hash equally and share the same string representation, so that
        ranges can be used in sets and as dictionary keys.
        """
        for r1, r2 in itertools.combinations(all_ranges, 2):
            if r1 == r2:
                assert hash(r1) == hash(r2)
                assert str(r1) == str(r2)
            else:
                assert str(r1) != str(r2)

        # The string representation is a faithful encoding, so it cannot collapse distinct ranges
        assert len({str(x) for x in all_ranges}) == len(set(all_ranges))

    def test_string_representation_round_trips(self, all_ranges):
        """Tests that every range can be recovered from its string representation."""
        for uarch_range in all_ranges:
            assert MicroarchitectureRange.from_string(str(uarch_range)) == uarch_range

    def test_containment_is_a_partial_order(self, sample_ranges):
        """Tests that containment between ranges is reflexive, antisymmetric and transitive."""
        for uarch_range in sample_ranges:
            assert uarch_range <= uarch_range

        for r1, r2 in itertools.permutations(sample_ranges, 2):
            if r1 <= r2 and r2 <= r1:
                assert r1 == r2

        for r1, r2, r3 in itertools.permutations(sample_ranges, 3):
            if r1 <= r2 and r2 <= r3:
                assert r1 <= r3

    def test_containment_agrees_with_the_microarchitectures_in_range(self, sample_ranges):
        """Tests that when a range contains another, it also contains all of its
        microarchitectures.
        """
        for r1, r2 in itertools.permutations(sample_ranges, 2):
            if r1 <= r2:
                assert all(x in r2 for x in r1)

    def test_a_range_supports_neither_union_nor_intersection(self):
        """Tests that a single range offers neither ``|`` nor ``&``.

        A range is closed under neither operation, since the microarchitecture partial order is
        not a lattice. Both live on MicroarchitectureRangeList, where they can be total, rather
        than being offered here in a form that fails on some inputs.
        """
        r1 = MicroarchitectureRange.from_string("armv8.6a:")
        r2 = MicroarchitectureRange.from_string("neoverse_n1:")

        with pytest.raises(TypeError, match="unsupported operand"):
            r1 & r2  # pylint: disable=pointless-statement
        with pytest.raises(TypeError, match="unsupported operand"):
            r1 | r2  # pylint: disable=pointless-statement


#: Pairs of ranges whose intersection has no unique boundary, so that it cannot be expressed as a
#: single range. They all come from the ``aarch64`` family, where ``ampere1``/``ampere1a`` and the
#: ``neoverse`` chips have two parents each.
AMBIGUOUS_RANGE_PAIRS = list(
    itertools.product(
        ["armv8.3a:", "armv8.4a:", "armv8.5a:", "armv8.6a:", "armv9.0a:"],
        ["cortex_a72:", "neoverse_n1:"],
    )
) + list(
    itertools.combinations(
        [":ampere1", ":ampere1a", ":neoverse_n2", ":neoverse_v1", ":neoverse_v2"], 2
    )
)


class TestMicroarchitectureRangeLists:
    @pytest.fixture(scope="class")
    def sample_lists(self):
        """A selection of unions, covering the interesting parts of both the x86_64 and the
        aarch64 DAGs, for the properties that need to compare unions pairwise.
        """
        names = [
            # x86_64, which is a lattice, including both sides of a bifurcation
            "x86_64",
            "x86_64_v2",
            "x86_64_v4",
            "broadwell",
            "mic_knl",
            "skylake",
            "cascadelake",
            "cannonlake",
            "icelake",
            "zen4",
            # aarch64, which is not a lattice
            "aarch64",
            "armv8.2a",
            "armv8.6a",
            "cortex_a72",
            "neoverse_n1",
            "ampere1",
            "ampere1a",
        ]
        result = [MicroarchitectureRangeList()]
        for name in names:
            uarch = archspec.cpu.TARGETS[name]
            result.append(MicroarchitectureRangeList([MicroarchitectureRange(lo=uarch)]))
            result.append(MicroarchitectureRangeList([MicroarchitectureRange(hi=uarch)]))

        # Unions with more than one member, including one crossing two architecture families
        result.extend(
            MicroarchitectureRangeList.from_string(x)
            for x in [
                "x86_64_v2:,aarch64:",
                "broadwell:skylake,ampere1:",
                "mic_knl:,x86_64:mic_knl",
                "cascadelake:,cannonlake:",
            ]
        )
        return result

    @pytest.mark.parametrize(
        "list_str,expected_str",
        [
            # A single range, in each of its forms
            ("broadwell:skylake", "broadwell:skylake"),
            ("broadwell:", "broadwell:"),
            (":skylake", "x86_64:skylake"),
            ("broadwell", "broadwell"),
            # Members are sorted, so that the representation is stable
            ("zen4:,broadwell:", "broadwell:,zen4:"),
            ("  broadwell : skylake , zen4 ", "broadwell:skylake,zen4"),
            # Members from different architecture families can be joined
            ("x86_64,aarch64", "aarch64,x86_64"),
            # Duplicates and members contained in another member are dropped
            ("broadwell:,broadwell:", "broadwell:"),
            ("x86_64:,broadwell:skylake", "x86_64:"),
            ("broadwell:skylake,x86_64:", "x86_64:"),
            ("skylake,broadwell:icelake", "broadwell:icelake"),
            # Empty members are dropped
            ("{},broadwell:", "broadwell:"),
            (":,broadwell:", "broadwell:"),
            # The empty union
            ("{}", "{}"),
        ],
    )
    def test_list_from_string(self, list_str, expected_str):
        """Tests that a union can be parsed from its string representation, and that it is
        normalized on construction.
        """
        assert str(MicroarchitectureRangeList.from_string(list_str)) == expected_str

    @pytest.mark.parametrize(
        "list_str,exception",
        [
            ("broadwell:skylake:icelake,zen4:", InvalidRange),
            ("broadwell:,not_a_target", ValueError),
            ("broadwell:,", ValueError),
        ],
    )
    def test_list_from_string_errors(self, list_str, exception):
        """Tests that parsing an invalid union from a string raises."""
        with pytest.raises(exception):
            MicroarchitectureRangeList.from_string(list_str)

    def test_empty_list(self):
        """Tests the properties of the union with no members."""
        empty = MicroarchitectureRangeList()

        assert empty.empty is True
        assert empty.ranges == ()
        assert len(empty) == 0
        assert list(empty) == []
        assert "broadwell" not in empty
        assert str(empty) == "{}"
        assert empty == MicroarchitectureRangeList.from_string("{}")
        assert empty == MicroarchitectureRangeList([MicroarchitectureRange()])

    def test_list_contains(self):
        """Tests that a union holds the microarchitectures of all its members, and nothing
        else.
        """
        uarch_list = MicroarchitectureRangeList.from_string("broadwell:skylake,neoverse_n1:")

        assert "broadwell" in uarch_list
        assert "skylake" in uarch_list
        assert "neoverse_n1" in uarch_list
        assert "ampere1" in uarch_list
        assert archspec.cpu.TARGETS["skylake"] in uarch_list
        assert "haswell" not in uarch_list
        assert "icelake" not in uarch_list
        assert "cortex_a72" not in uarch_list

    @pytest.mark.parametrize("item", [42, None, 3.14])
    def test_list_contains_rejects_invalid_types(self, item):
        """Tests that testing membership of an object that is not a microarchitecture, nor a
        string, raises a TypeError, even when the union is empty.
        """
        for uarch_list in (
            MicroarchitectureRangeList.from_string("broadwell:icelake"),
            MicroarchitectureRangeList(),
        ):
            with pytest.raises(TypeError, match="only objects of string or Microarchitecture"):
                item in uarch_list  # pylint: disable=pointless-statement

    def test_list_iteration_is_deterministic_and_topological(self):
        """Tests that iterating a union yields each microarchitecture once, in a stable order
        with ancestors always coming before their descendants.
        """
        # The two members overlap, so a microarchitecture must not be yielded twice
        uarch_list = MicroarchitectureRangeList.from_string("x86_64:skylake,broadwell:icelake")
        result = list(uarch_list)

        assert result == list(uarch_list), "iteration order is not stable"
        assert len(result) == len(uarch_list) == len(set(result))
        assert set(result) == set(
            archspec.cpu.microarchitecture_range(lo="x86_64", hi="skylake")
        ) | set(archspec.cpu.microarchitecture_range(lo="broadwell", hi="icelake"))
        for index, uarch in enumerate(result):
            descendants_before = [x for x in result[:index] if uarch < x]
            assert not descendants_before, f"{uarch} comes after its descendants"

    @pytest.mark.parametrize(
        "l1_str,l2_str,expected_str",
        [
            # The four shapes where a single range cannot express the intersection
            ("armv9.0a:", "neoverse_n1:", "neoverse_n2:,neoverse_v2:"),
            ("armv8.6a:", "neoverse_n1:", "ampere1:,ampere1a:"),
            (":ampere1", ":ampere1a", "aarch64:armv8.6a,aarch64:neoverse_n1"),
            (":neoverse_n2", ":neoverse_v2", "aarch64:armv9.0a,aarch64:neoverse_n1"),
            # Intersections that a single range does express
            ("skylake:icelake", "x86_64_v2:cascadelake", "skylake:cascadelake"),
            ("x86_64:skylake", "skylake:icelake", "skylake"),
            (":cascadelake", ":cannonlake", "x86_64:skylake"),
            ("x86_64_v2:icelake", ":zen2", "x86_64_v2:x86_64_v3"),
            # One boundary open on each side
            ("broadwell:", ":cascadelake", "broadwell:cascadelake"),
            # Both unbounded above, so the result stays open
            ("x86_64_v2:", "x86_64_v3:", "x86_64_v3:"),
            ("x86_64_v2:", "zen4:", "zen4:"),
            # Collapsing to a single microarchitecture
            ("broadwell", "broadwell", "broadwell"),
            ("armv8.6a:", "neoverse_n1:ampere1", "ampere1"),
            # Different families give the empty union rather than raising
            ("broadwell:icelake", "aarch64:", "{}"),
            ("broadwell:", ":neoverse_n1", "{}"),
            # The empty union absorbs anything
            ("broadwell:skylake", "{}", "{}"),
            # Intersections of unions with more than one member
            ("x86_64:,aarch64:", "broadwell:,neoverse_n1:", "broadwell:,neoverse_n1:"),
            ("x86_64:broadwell,zen4:", "aarch64:", "{}"),
        ],
    )
    def test_list_intersection(self, l1_str, l2_str, expected_str):
        """Tests that intersecting two unions gives the expected union, and that it commutes."""
        l1 = MicroarchitectureRangeList.from_string(l1_str)
        l2 = MicroarchitectureRangeList.from_string(l2_str)
        expected = MicroarchitectureRangeList.from_string(expected_str)

        assert l1 & l2 == expected
        assert l2 & l1 == expected
        assert str(l1 & l2) == expected_str

    @pytest.mark.parametrize("r1_str,r2_str", AMBIGUOUS_RANGE_PAIRS)
    def test_list_intersection_is_total(self, r1_str, r2_str):
        """Tests that the intersection of two unions never raises, even for the pairs of ranges
        whose intersection has no unique boundary, and that it is the exact set intersection.
        """
        l1 = MicroarchitectureRangeList.from_string(r1_str)
        l2 = MicroarchitectureRangeList.from_string(r2_str)
        intersection = l1 & l2

        assert len(intersection.ranges) > 1, "an ambiguous boundary needs more than one range"
        assert set(intersection) == set(l1) & set(l2)
        assert intersection <= l1
        assert intersection <= l2

    def test_list_intersection_keeps_one_member_when_boundaries_are_unique(self, sample_lists):
        """Tests that a union grows extra members only when it has to.

        Whenever the intersection of two single ranges has unique boundaries, the result is that
        one range, so the number of members does not creep up on the common case.
        """
        ranges = [x for uarch_list in sample_lists for x in uarch_list.ranges]
        multi_member = 0
        for r1, r2 in itertools.combinations(ranges, 2):
            intersection = MicroarchitectureRangeList([r1]) & MicroarchitectureRangeList([r2])
            assert set(intersection) == set(r1) & set(r2)
            if len(intersection.ranges) > 1:
                multi_member += 1
                # Only same family pairs can need more than one member
                assert r1.family == r2.family
        assert multi_member, "no pair needed more than one member"

    def test_list_intersection_is_the_exact_set_intersection(self, sample_lists):
        """Tests that the intersection of two unions holds exactly the microarchitectures that
        belong to both of them, and is contained in each of them.
        """
        for l1, l2 in itertools.combinations(sample_lists, 2):
            intersection = l1 & l2
            assert set(intersection) == set(l1) & set(l2)
            assert intersection <= l1
            assert intersection <= l2

    def test_list_intersection_algebraic_laws(self, sample_lists):
        """Tests that intersection is idempotent, commutative, and that the empty union absorbs
        any other union.
        """
        empty = MicroarchitectureRangeList()
        for uarch_list in sample_lists:
            assert uarch_list & uarch_list == uarch_list
            assert uarch_list & empty == empty
            assert empty & uarch_list == empty

        for l1, l2 in itertools.combinations(sample_lists, 2):
            assert l1 & l2 == l2 & l1

    def test_list_intersection_is_associative(self, sample_lists):
        """Tests that intersection is associative. Unlike the single range case this needs no
        exception handling, since the operation is total.
        """
        for l1, l2, l3 in itertools.combinations(sample_lists, 3):
            assert (l1 & l2) & l3 == l1 & (l2 & l3)

    def test_list_intersection_rejects_invalid_types(self):
        """Tests that a union can only be intersected with another union."""
        uarch_list = MicroarchitectureRangeList.from_string("broadwell:")
        with pytest.raises(TypeError):
            uarch_list & MicroarchitectureRange.from_string("broadwell:")

    @pytest.mark.parametrize(
        "l1_str,l2_str,expected",
        [
            # A single member inside a single member
            ("broadwell:icelake", "x86_64_v2:", True),
            ("x86_64_v2:", "broadwell:icelake", False),
            # Every member is inside a member of the other union
            ("broadwell:,neoverse_n1:", "x86_64:,aarch64:", True),
            ("x86_64:,aarch64:", "broadwell:,neoverse_n1:", False),
            # One member is inside, the other is not
            ("broadwell:,neoverse_n1:", "x86_64:", False),
            ("broadwell:", "x86_64:,aarch64:", True),
            # A union always contains itself
            ("broadwell:,neoverse_n1:", "broadwell:,neoverse_n1:", True),
            # The empty union is contained in every union
            ("{}", "broadwell:", True),
            ("broadwell:", "{}", False),
        ],
    )
    def test_list_containment(self, l1_str, l2_str, expected):
        """Tests that the comparison operators between unions implement subset semantics."""
        l1 = MicroarchitectureRangeList.from_string(l1_str)
        l2 = MicroarchitectureRangeList.from_string(l2_str)

        assert (l1 <= l2) is expected
        assert (l2 >= l1) is expected
        # The strict operators agree, except when the two unions are equal
        assert (l1 < l2) is (expected and l1 != l2)
        assert (l2 > l1) is (expected and l1 != l2)

    def test_list_containment_is_a_partial_order(self, sample_lists):
        """Tests that containment between unions is reflexive, antisymmetric and transitive."""
        for uarch_list in sample_lists:
            assert uarch_list <= uarch_list

        for l1, l2 in itertools.permutations(sample_lists, 2):
            if l1 <= l2 and l2 <= l1:
                assert l1 == l2

        for l1, l2, l3 in itertools.permutations(sample_lists, 3):
            if l1 <= l2 and l2 <= l3:
                assert l1 <= l3

    def test_list_containment_is_sound(self, sample_lists):
        """Tests that containment between unions is never claimed when the microarchitectures of
        one are not a subset of the microarchitectures of the other.

        Containment is checked member-wise, which is sufficient but not necessary, so the
        converse does not hold, see ``test_list_containment_is_conservative``.
        """
        for l1, l2 in itertools.permutations(sample_lists, 2):
            if l1 <= l2:
                assert set(l1) <= set(l2)
                assert all(x in l2 for x in l1)

    def test_list_containment_is_conservative(self):
        """Tests the documented approximation in containment: a member covered by two members of
        the other union, rather than by a single one, is not recognized.
        """
        narrow = MicroarchitectureRangeList.from_string("x86_64:icelake")
        wide = MicroarchitectureRangeList.from_string("x86_64:cascadelake,cannonlake:icelake")

        assert set(narrow) <= set(wide)
        assert not narrow <= wide

    def test_list_equality_agrees_with_hashing(self, sample_lists):
        """Tests that equal unions hash equally and share the same string representation, so
        that unions can be used in sets and as dictionary keys.
        """
        for l1, l2 in itertools.combinations(sample_lists, 2):
            if l1 == l2:
                assert hash(l1) == hash(l2)
                assert str(l1) == str(l2)
            else:
                assert str(l1) != str(l2)

        # The string representation is a faithful encoding, so it cannot collapse distinct unions
        assert len({str(x) for x in sample_lists}) == len(set(sample_lists))

    def test_list_string_representation_round_trips(self, sample_lists):
        """Tests that every union can be recovered from its string representation."""
        extra = [
            # A union of point ranges, which render as bare names
            MicroarchitectureRangeList.from_string("broadwell,zen4"),
            # A single member union, with each kind of boundary
            MicroarchitectureRangeList.from_string("broadwell"),
            MicroarchitectureRangeList.from_string("broadwell:"),
            MicroarchitectureRangeList.from_string(":broadwell"),
            MicroarchitectureRangeList.from_string("x86_64:broadwell"),
        ]
        for uarch_list in list(sample_lists) + extra:
            assert MicroarchitectureRangeList.from_string(str(uarch_list)) == uarch_list

    def test_list_repr(self):
        """Tests that the repr of a union shows its members."""
        uarch_list = MicroarchitectureRangeList.from_string("broadwell:skylake")
        assert repr(uarch_list) == (
            "MicroarchitectureRangeList([MicroarchitectureRange("
            "lo=Microarchitecture('broadwell'), hi=Microarchitecture('skylake'))])"
        )


class TestConcreteMicroarchitectures:
    """Tests recovering a single microarchitecture from a range or a union of ranges."""

    @pytest.mark.parametrize(
        "range_str,expected",
        [
            # A bare name is the range holding that microarchitecture only
            ("broadwell", "broadwell"),
            ("broadwell:broadwell", "broadwell"),
            (":x86_64", "x86_64"),
            # Ranges spanning more than one microarchitecture are not concrete
            ("broadwell:skylake", None),
            ("broadwell:", None),
            (":skylake", None),
            # The empty range is not concrete either
            ("{}", None),
            # An open range with a single member today is still not concrete, since a
            # descendant added to the database in the future would fall in it
            ("mic_knl:", None),
        ],
    )
    def test_range_concrete(self, range_str, expected):
        """Tests that a range is concrete exactly when its boundaries are the same
        microarchitecture, which is a property of the boundaries and not of the database.
        """
        result = MicroarchitectureRange.from_string(range_str).concrete
        if expected is None:
            assert result is None
        else:
            assert result is archspec.cpu.TARGETS[expected]

    @pytest.mark.parametrize(
        "list_str,expected",
        [
            ("broadwell", "broadwell"),
            ("broadwell:broadwell", "broadwell"),
            # More than one member is never concrete, even when every member is
            ("broadwell,zen4", None),
            # A single member that is not concrete
            ("broadwell:skylake", None),
            ("mic_knl:", None),
            # The empty union
            ("{}", None),
        ],
    )
    def test_list_concrete(self, list_str, expected):
        """Tests that a union is concrete exactly when it has one concrete member."""
        result = MicroarchitectureRangeList.from_string(list_str).concrete
        if expected is None:
            assert result is None
        else:
            assert result is archspec.cpu.TARGETS[expected]

    def test_concrete_is_not_the_same_question_as_length(self):
        """Tests the case that motivates having ``concrete`` at all: ``len() == 1`` is true both
        for a genuinely concrete range and for an open range that happens to hold one
        microarchitecture today, and the two must not be conflated.
        """
        concrete = MicroarchitectureRangeList.from_string("mic_knl")
        open_range = MicroarchitectureRangeList.from_string("mic_knl:")

        assert len(concrete) == len(open_range) == 1
        assert list(concrete) == list(open_range)

        assert concrete.concrete is archspec.cpu.TARGETS["mic_knl"]
        assert open_range.concrete is None
        assert concrete != open_range

    def test_concrete_round_trips_through_the_microarchitecture(self):
        """Tests that a concrete union yields back the very object from TARGETS, so that vendor,
        features and compiler information survive the round trip.
        """
        for name in ("broadwell", "neoverse_n1", "x86_64"):
            recovered = MicroarchitectureRangeList.from_string(name).concrete
            assert recovered is archspec.cpu.TARGETS[name]
            assert MicroarchitectureRangeList.from_string(str(recovered)).concrete is recovered

    def test_intersection_collapsing_to_one_microarchitecture_is_concrete(self):
        """Tests that an intersection that narrows down to a single microarchitecture reports as
        concrete, which is how a client detects that a constraint has been fully resolved.
        """
        r1 = MicroarchitectureRangeList.from_string("x86_64:skylake")
        r2 = MicroarchitectureRangeList.from_string("skylake:icelake")

        assert (r1 & r2).concrete is archspec.cpu.TARGETS["skylake"]

    def test_ambiguous_intersection_is_not_concrete(self):
        """Tests that an intersection returned as several members is not concrete, even though
        each of its members is an open range."""
        result = MicroarchitectureRangeList.from_string(
            "armv9.0a:"
        ) & MicroarchitectureRangeList.from_string("neoverse_n1:")

        assert len(result.ranges) == 2
        assert result.concrete is None


class TestUnknownMicroarchitectureErrors:
    """Tests that every parsing failure is catchable as an ArchspecError."""

    @pytest.mark.parametrize(
        "bad_str",
        ["not_a_target", "not_a_target:", ":not_a_target", "broadwell:not_a_target"],
    )
    def test_unknown_names_raise_archspec_errors(self, bad_str):
        """Tests that an unknown microarchitecture name raises UnknownMicroarchitecture, so a
        caller can catch ArchspecError instead of a bare ValueError.
        """
        with pytest.raises(UnknownMicroarchitecture):
            MicroarchitectureRange.from_string(bad_str)
        with pytest.raises(ArchspecError):
            MicroarchitectureRangeList.from_string(bad_str)

    def test_unknown_name_from_microarchitecture(self):
        """Tests the same for the Microarchitecture entry point."""
        with pytest.raises(UnknownMicroarchitecture, match="unknown micro-architecture"):
            Microarchitecture.from_string("not_a_target")

    def test_unknown_name_in_a_comparison(self):
        """Tests that comparing against an unknown name also raises an ArchspecError, rather than
        the bare ValueError the coercion decorator used to produce.
        """
        with pytest.raises(UnknownMicroarchitecture, match="not a valid target name"):
            _ = archspec.cpu.TARGETS["broadwell"] <= "not_a_target"

    def test_every_parse_failure_is_an_archspec_error(self):
        """Tests that both failure modes of range parsing share the ArchspecError base, so one
        except clause covers unknown names and malformed ranges alike.
        """
        for bad_str in ("not_a_target", "broadwell:skylake:icelake", "skylake:broadwell"):
            with pytest.raises(ArchspecError):
                MicroarchitectureRangeList.from_string(bad_str)

    def test_unknown_microarchitecture_is_still_a_value_error(self):
        """Tests that the new exception keeps ValueError as a base, so existing callers that
        catch ValueError are unaffected.
        """
        assert issubclass(UnknownMicroarchitecture, ValueError)
        assert issubclass(UnknownMicroarchitecture, ArchspecError)
        assert issubclass(InvalidRange, ArchspecError)
