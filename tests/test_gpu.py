# Copyright 2019-2026 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
import subprocess

import jsonschema
import pytest

import archspec.gpu
import archspec.gpu.amd
import archspec.gpu.nvidia
import archspec.gpu.schema
from archspec.cpu.microarchitecture import (
    InvalidCompilerVersion,
    UnsupportedMicroarchitecture,
)
from archspec.gpu.gpu import GPU, ComputeCapability, GFXTarget, VendorPciCode
from archspec.gpu.gpu_microarch import TARGETS, GPUMicroarch


def mock_smi(stdout, returncode=0):
    """Return a ``subprocess.run`` replacement that yields the given stdout."""

    def _run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout)

    return _run


@pytest.mark.parametrize(
    "combined,expected",
    [
        ("0x2C0210DE", ("0x2c02", "0x10de")),
        ("0x233010DE", ("0x2330", "0x10de")),
    ],
)
def test_nvidia_pci_device_id_parsing(combined, expected):
    """Test that a combined PCI device ID splits into lowercase (device, vendor) codes."""
    assert archspec.gpu.nvidia._parse_pci_device_id(combined) == expected


@pytest.mark.parametrize("bad_id", ["0x2C0210", "2C0210DE00", "0xZZZZ10DE0", "0xZZZZ10DE"])
def test_nvidia_pci_device_id_invalid(bad_id):
    """Test that a malformed PCI device ID raises ValueError."""
    with pytest.raises(ValueError):
        archspec.gpu.nvidia._parse_pci_device_id(bad_id)


def test_nvidia_smi_info_parses_smi_output(monkeypatch):
    """Test that nvidia.smi_info parses nvidia-smi CSV output into GPU objects."""
    nvidia_smi_csv = (
        "NVIDIA GeForce RTX 5080, 595.58.03, 0x2C0210DE, 12.0\n"
        "NVIDIA H100 PCIe, 550.54.15, 0x233010DE, 9.0\n"
    )
    monkeypatch.setattr(archspec.gpu.nvidia.subprocess, "run", mock_smi(nvidia_smi_csv))

    gpus = archspec.gpu.nvidia.smi_info()

    assert len(gpus) == 2
    assert all(gpu.vendor == "nvidia" for gpu in gpus)
    assert all(gpu.vendor_pci_code == "0x10de" for gpu in gpus)

    assert gpus[0].name == "NVIDIA GeForce RTX 5080"
    assert gpus[0].driver_version == "595.58.03"
    assert gpus[0].component_pci_code == "0x2c02"
    assert gpus[0].compute_capability == ComputeCapability(12, 0)

    assert gpus[1].name == "NVIDIA H100 PCIe"
    assert gpus[1].driver_version == "550.54.15"
    assert gpus[1].component_pci_code == "0x2330"
    assert gpus[1].compute_capability == ComputeCapability(9, 0)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("9.0", ComputeCapability(9, 0)),
        ("12.0", ComputeCapability(12, 0)),
        ("90", ComputeCapability(9, 0)),
        ("90a", ComputeCapability(9, 0, "a")),
        ("100f", ComputeCapability(10, 0, "f")),
        ("10.3a", ComputeCapability(10, 3, "a")),
        (" 90 ", ComputeCapability(9, 0)),
    ],
)
def test_compute_capability_from_str(text, expected):
    """Both the dotted nvidia-smi form and the decimal-free form parse to the same object."""
    assert ComputeCapability.from_str(text) == expected


@pytest.mark.parametrize("name", ["90", "90a", "100f", "120", "75"])
def test_compute_capability_name_is_decimal_free(name):
    """The canonical name is the ``XYs`` form, and it round-trips through from_str."""
    capability = ComputeCapability.from_str(name)
    assert capability.name == name
    assert str(capability) == name
    assert "." not in capability.name


def test_compute_capability_dotted_input_normalizes():
    """nvidia-smi style ``X.Y`` input is emitted in the decimal-free notation."""
    assert ComputeCapability.from_str("9.0").name == "90"
    assert ComputeCapability.from_str("12.0").name == "120"


def test_compute_capability_suffix_is_distinct():
    """A suffixed capability is a different target than its unsuffixed base."""
    assert ComputeCapability(9, 0) != ComputeCapability(9, 0, "a")
    assert len({ComputeCapability(9, 0), ComputeCapability(9, 0, "a")}) == 2


@pytest.mark.parametrize(
    "bad", ["", "9", "9.", ".0", "9.00", "9.0.1", "a90", "90-", "9 0", "[N/A]"]
)
def test_compute_capability_from_str_invalid(bad):
    """Malformed compute capabilities raise ValueError."""
    with pytest.raises(ValueError):
        ComputeCapability.from_str(bad)


def test_rocm_smi_info_handles_malformed_json(monkeypatch):
    """Test that amd.smi_info returns no GPUs when rocm-smi emits unparseable output."""
    monkeypatch.setattr(archspec.gpu.amd.subprocess, "run", mock_smi("not json"))

    assert archspec.gpu.amd.smi_info() == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {
            "name": "NVIDIA H100 PCIe",
            "vendor": "nvidia",
            "driver_version": "550.54.15",
            "vendor_pci_code": VendorPciCode.NVIDIA,
            "component_pci_code": "0x2330",
            "compute_capability": ComputeCapability(9, 0),
        },
        {
            "name": "AMD Instinct MI300A",
            "vendor": "amd",
            "driver_version": "6.16.13",
            "vendor_pci_code": VendorPciCode.AMD,
            "component_pci_code": "0x74a0",
            "gfx_target": GFXTarget(9, 4, 2),
        },
    ],
)
def test_round_trip_dict(kwargs):
    """A GPU survives a round trip through to_dict/from_dict."""
    gpu = GPU(**kwargs)
    assert GPU.from_dict(gpu.to_dict()) == gpu


def test_equality_and_hash():
    """Equal GPU objects compare equal, hash equal, and deduplicate in sets."""
    kwargs = {
        "name": "AMD Instinct MI300A",
        "vendor": "amd",
        "vendor_pci_code": VendorPciCode.AMD,
        "component_pci_code": "0x74a0",
        "gfx_target": GFXTarget(9, 4, 2),
    }
    first = GPU(**kwargs)
    second = GPU(**kwargs)
    other_driver = GPU(**kwargs, driver_version="6.16.13")

    assert first == second
    assert hash(first) == hash(second)
    assert first != other_driver
    assert first != "gfx942"
    assert len({first, second}) == 1


@pytest.fixture(name="nvidia_graph")
def _nvidia_graph():
    """A small NVIDIA compatibility graph: 80 <- 86 <- 89, and 90 off the root."""
    nvcc = lambda arch, since: {  # noqa: E731
        "nvcc": [
            {"versions": f"{since}:", "flags": f"-gencode arch=compute_{arch},code=sm_{arch}"}
        ]
    }
    root = GPUMicroarch("nvidia", "generic")
    cc80 = GPUMicroarch("80", "nvidia", parents=[root], compilers=nvcc("80", "11.0"))
    cc86 = GPUMicroarch("86", "nvidia", parents=[cc80], compilers=nvcc("86", "11.1"))
    cc89 = GPUMicroarch("89", "nvidia", parents=[cc86])
    cc90 = GPUMicroarch("90", "nvidia", parents=[root], compilers=nvcc("90", "11.8"))
    return {"nvidia": root, "80": cc80, "86": cc86, "89": cc89, "90": cc90}


def test_microarch_ancestors_and_family(nvidia_graph):
    assert nvidia_graph["89"].ancestors == [
        nvidia_graph["86"],
        nvidia_graph["80"],
        nvidia_graph["nvidia"],
    ]
    assert nvidia_graph["nvidia"].ancestors == []
    for microarch in nvidia_graph.values():
        assert microarch.family is nvidia_graph["nvidia"]


def test_microarch_ordering(nvidia_graph):
    """Ordering is set inclusion over the ancestor DAG, so unrelated nodes are incomparable."""
    cc80, cc89, cc90 = nvidia_graph["80"], nvidia_graph["89"], nvidia_graph["90"]
    assert cc80 < cc89 and cc89 > cc80
    assert cc80 <= cc89 and cc80 <= cc80 and cc89 >= cc89
    assert not cc89 < cc90 and not cc89 > cc90
    assert not cc89 < cc89
    assert nvidia_graph["nvidia"] < cc90
    with pytest.raises(TypeError):
        _ = cc80 < "89"  # type: ignore[operator]


def test_microarch_equality_and_hash(nvidia_graph):
    root = nvidia_graph["nvidia"]
    same = GPUMicroarch("80", "nvidia", parents=[root], compilers=nvidia_graph["80"].compilers)
    no_parents = GPUMicroarch("80", "nvidia")
    assert same == nvidia_graph["80"]
    assert hash(same) == hash(nvidia_graph["80"])
    assert no_parents != nvidia_graph["80"]
    assert nvidia_graph["80"] != "80"
    assert len({same, nvidia_graph["80"]}) == 1


def test_microarch_to_dict(nvidia_graph):
    assert nvidia_graph["86"].to_dict() == {
        "name": "86",
        "vendor": "nvidia",
        "parents": ["80"],
        "compilers": nvidia_graph["86"].compilers,
    }
    assert nvidia_graph["nvidia"].to_dict() == {
        "name": "nvidia",
        "vendor": "generic",
        "parents": [],
        "compilers": {},
    }


def test_microarch_optimization_flags(nvidia_graph):
    cc86 = nvidia_graph["86"]
    assert cc86.optimization_flags("nvcc", "12.4") == "-gencode arch=compute_86,code=sm_86"
    assert cc86.optimization_flags("nvcc", "11.1") == "-gencode arch=compute_86,code=sm_86"
    # Unknown compiler anywhere in the lineage: nothing to say
    assert cc86.optimization_flags("clang", "18.1") == ""
    # Version too old for this target
    with pytest.raises(UnsupportedMicroarchitecture, match="11.1:"):
        cc86.optimization_flags("nvcc", "11.0")
    # Compiler known to an ancestor but not to this target
    with pytest.raises(UnsupportedMicroarchitecture, match="up to the '86"):
        nvidia_graph["89"].optimization_flags("nvcc", "12.4")
    with pytest.raises(InvalidCompilerVersion):
        cc86.optimization_flags("nvcc", "12.4-rc1")


def test_microarch_optimization_flags_bounded_range():
    amd = GPUMicroarch("amd", "generic")
    gfx = GPUMicroarch(
        "gfx803",
        "amd",
        parents=[amd],
        compilers={"hipcc": [{"versions": "3.0:5.7", "flags": "--offload-arch={name}"}]},
    )
    assert gfx.optimization_flags("hipcc", "5.7") == "--offload-arch=gfx803"
    with pytest.raises(UnsupportedMicroarchitecture):
        gfx.optimization_flags("hipcc", "6.0")


@pytest.mark.parametrize(
    "gpu,expected",
    [
        # NVIDIA resolves to the most capable node for the silicon: a, then f, then plain
        (GPU(vendor="nvidia", compute_capability=ComputeCapability(10, 0)), "100a"),
        (GPU(vendor="nvidia", compute_capability=ComputeCapability(9, 0)), "90a"),
        (GPU(vendor="nvidia", compute_capability=ComputeCapability(7, 5)), "75"),
        # AMD resolves to the exact target ID, with or without an xnack mode
        (GPU(vendor="amd", gfx_target=GFXTarget(9, 4, 2)), "gfx942"),
        (GPU(vendor="amd", gfx_target=GFXTarget(9, 0, 10, xnack="-")), "gfx90a:xnack-"),
    ],
)
def test_from_gpu_returns_catalogue_entry(gpu, expected):
    """A detected GPU maps to the TARGETS object itself, with its ancestry attached."""
    microarch = GPUMicroarch.from_gpu(gpu)
    assert microarch is TARGETS[expected]
    assert microarch.ancestors


def test_from_gpu_unknown_device_has_no_parents():
    """A device the JSON doesn't know is still reported, but as a parentless node."""
    gpu = GPU(vendor="nvidia", compute_capability=ComputeCapability(13, 0))
    microarch = GPUMicroarch.from_gpu(gpu)
    assert microarch == GPUMicroarch("130", "nvidia")
    assert microarch.parents == [] and microarch.family is microarch
    assert all(not microarch >= t for t in TARGETS.values())


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("gfx90a", "gfx90a"),
        ("gfx90a:sramecc+:xnack-", "gfx90a:xnack-"),
        ("gfx90a:xnack+", "gfx90a:xnack+"),
        ("gfx942:sramecc+", "gfx942"),  # sramecc is not modelled
        ("GFX1100:XNACK-", "gfx1100:xnack-"),
    ],
)
def test_gfx_target_keeps_xnack(raw, expected):
    target = GFXTarget.from_str(raw)
    assert target.name == expected
    assert GFXTarget.from_str(target.name) == target


def test_gfx_target_xnack_modes_are_distinct():
    assert GFXTarget(9, 0, 10, xnack="-") != GFXTarget(9, 0, 10)
    assert GFXTarget(9, 0, 10, xnack="-") != GFXTarget(9, 0, 10, xnack="+")
    assert len({GFXTarget(9, 0, 10, xnack="-"), GFXTarget(9, 0, 10, xnack="-")}) == 1


def test_validate_gpu_json_file():
    """The GPU microarchitecture JSON file loads and validates against its schema."""
    json_data = archspec.gpu.schema.TARGETS_JSON.data
    schema = archspec.gpu.schema.TARGETS_JSON_SCHEMA.data
    jsonschema.validate(json_data, schema)
    assert "90" in json_data["microarchitectures"]


def test_gpu_json_dir_override(tmp_path, monkeypatch):
    """ARCHSPEC_GPU_DIR redirects where microarchitectures.json is read from."""
    (tmp_path / "microarchitectures.json").write_text('{"microarchitectures": {}}')
    monkeypatch.setenv(archspec.gpu.schema.DIR_FROM_ENVIRONMENT, str(tmp_path))
    assert archspec.gpu.schema._json_file("microarchitectures.json", allow_custom=True) == (
        tmp_path / "microarchitectures.json"
    )
    assert archspec.gpu.schema._json_file("microarchitectures_schema.json").parent.name == "gpu"


def test_validate_gpu_json_files():
    """The GPU microarchitecture JSON validates against its schema."""
    jsonschema.validate(
        archspec.gpu.schema.TARGETS_JSON.data, archspec.gpu.schema.TARGETS_JSON_SCHEMA.data
    )


def test_targets_are_connected():
    """TARGETS resolves every ``from`` entry to the shared object for that name."""
    raw = archspec.gpu.schema.TARGETS_JSON["microarchitectures"]
    assert set(TARGETS) == set(raw)
    for name, values in raw.items():
        target = TARGETS[name]
        assert target.name == name and target.vendor == values["vendor"]
        assert [p.name for p in target.parents] == values["from"]
        assert all(p is TARGETS[p.name] for p in target.parents)
        assert target.compilers == values.get("compilers", {})


def test_targets_roots_and_families():
    roots = {name for name, t in TARGETS.items() if not t.parents}
    assert roots == {"nvidia", "amd"}
    for target in TARGETS.values():
        assert target.family.name in roots
        assert target.family.vendor == "generic"


@pytest.mark.parametrize(
    "host,target,expected",
    [
        ("100a", "100", True),  # a B200 runs sm_100 SASS
        ("100a", "100f", True),  # and sm_100f, the family target
        ("103a", "100f", True),  # a B300 is in the same family
        ("103a", "100a", False),  # but architecture-specific code is exact-match only
        ("89", "80", True),  # minor-version forward compatibility within a major
        ("90", "89", False),  # never across majors
        ("101a", "100", False),  # 10.1 is isolated
        ("gfx90a:xnack-", "gfx90a", True),  # either xnack mode runs xnack-agnostic code
        ("gfx90a:xnack-", "gfx90a:xnack+", False),  # but the modes do not run each other's
        ("gfx942", "amd", True),
    ],
)
def test_targets_ordering(host, target, expected):
    assert (TARGETS[host] >= TARGETS[target]) is expected


def test_targets_optimization_flags():
    assert (
        TARGETS["89"].optimization_flags("nvcc", "12.4") == "-gencode arch=compute_89,code=sm_89"
    )
    assert TARGETS["100a"].optimization_flags("clang", "20.1") == "--cuda-gpu-arch=sm_100a"
    assert TARGETS["gfx90a:xnack-"].optimization_flags("hipcc", "6.4") == (
        "--offload-arch=gfx90a:xnack-"
    )
    with pytest.raises(UnsupportedMicroarchitecture):
        TARGETS["70"].optimization_flags("nvcc", "13.0")


@pytest.mark.parametrize(
    "node,expected",
    [
        ("100a", "10.0"),
        ("100f", "10.0"),
        ("75", "7.5"),
        ("121a", "12.1"),
        ("gfx90a:xnack-", "gfx90a"),
        ("gfx942", "gfx942"),
        ("nvidia", "nvidia"),
    ],
)
def test_display_name_drops_target_suffix(node, expected):
    """display_name is the device's own identifier; str() and name are the node name."""
    assert TARGETS[node].display_name == expected
    assert str(TARGETS[node]) == TARGETS[node].name == node


def test_str_of_detected_gpu_is_node_name():
    gpu = GPU(vendor="nvidia", compute_capability=ComputeCapability(10, 0))
    microarch = GPUMicroarch.from_gpu(gpu)
    assert str(microarch) == "100a"
    assert microarch.display_name == "10.0"
