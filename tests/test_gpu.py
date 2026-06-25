# Copyright 2019-2026 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
import json
import subprocess

import pytest

import archspec.gpu.detect


def make_pci_devices(root, devices):
    """Create fake sysfs PCI device directories under ``root``.

    Args:
        root: directory to populate (a ``tmp_path``).
        devices: iterable of ``(class_code, vendor_id, device_id)`` tuples.
    """
    for i, (class_code, vendor_id, device_id) in enumerate(devices):
        device_dir = root / f"0000:{i:02x}:00.0"
        device_dir.mkdir()
        (device_dir / "class").write_text(class_code)
        (device_dir / "vendor").write_text(vendor_id)
        (device_dir / "device").write_text(device_id)


def mock_smi(stdout, returncode=0):
    """Return a ``subprocess.run`` replacement that yields the given stdout."""

    def _run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout)

    return _run


def mock_which(*installed):
    """Return a ``shutil.which`` replacement that reports only ``installed`` tools."""
    return lambda name, *args, **kwargs: f"/usr/bin/{name}" if name in installed else None


# --- Stage 1: vendor detection (sysfs scan) ---


@pytest.mark.parametrize(
    "devices,expected",
    [
        ([], set()),
        ([("0x030000", "0x10de", "0x2c02")], {"nvidia"}),
        ([("0x120000", "0x1002", "0x74a0")], {"amd"}),
        (
            [("0x120000", "0x1002", "0x74a0"), ("0x030000", "0x8086", "0x56a0")],
            {"amd", "intel"},
        ),
        (
            [
                ("0x030000", "0x10de", "0x2c02"),
                ("0x120000", "0x1002", "0x74a0"),
                ("0x030000", "0x8086", "0x56a0"),
            ],
            {"nvidia", "amd", "intel"},
        ),
        ([("0x010000", "0x10de", "0x2c02")], set()),
        (
            [("0x030000", "0x10de", "0x2c02"), ("0x030000", "0x10de", "0x2204")],
            {"nvidia"},
        ),
        ([("0x030000", "0x1234", "0x0001")], set()),
    ],
)
def test_sysfs_scan_detects_vendors(tmp_path, monkeypatch, devices, expected):
    """Test that the sysfs PCI scan reports exactly the GPU vendors present."""
    make_pci_devices(tmp_path, devices)
    monkeypatch.setattr(archspec.gpu.detect, "SYSFS_PCI_DEVICES", str(tmp_path))

    assert {g.vendor for g in archspec.gpu.detect._scan_sysfs_pci_for_gpus()} == expected


def test_detect_amd_instinct_accelerator(tmp_path, monkeypatch):
    """Test that an AMD Instinct accelerator (PCI class 0x120000) is detected."""
    device_dir = tmp_path / "0000:c1:00.0"
    device_dir.mkdir()
    (device_dir / "class").write_text("0x120000")
    (device_dir / "vendor").write_text("0x1002")
    (device_dir / "device").write_text("0x74a0")
    monkeypatch.setattr(archspec.gpu.detect, "SYSFS_PCI_DEVICES", str(tmp_path))

    gpus = archspec.gpu.detect._scan_sysfs_pci_for_gpus()
    assert {g.vendor for g in gpus} == {"amd"}
    assert gpus[0].component_pci_code == "0x74a0"


# --- Stage 2: nvidia-smi parsing ---


@pytest.mark.parametrize(
    "combined,expected",
    [
        ("0x2C0210DE", ("0x2c02", "0x10de")),
        ("0x233010DE", ("0x2330", "0x10de")),
    ],
)
def test_nvidia_pci_device_id_parsing(combined, expected):
    """Test that a combined PCI device ID splits into lowercase (device, vendor) codes."""
    assert archspec.gpu.detect._parse_nvidia_pci_device_id(combined) == expected


@pytest.mark.parametrize("bad_id", ["0x2C0210", "2C0210DE00", "0xZZZZ10DE0"])
def test_nvidia_pci_device_id_invalid(bad_id):
    """Test that a malformed PCI device ID raises ValueError."""
    with pytest.raises(ValueError):
        archspec.gpu.detect._parse_nvidia_pci_device_id(bad_id)


@pytest.mark.parametrize(
    "compute_cap,expected",
    [
        ("9.0", "sm_90"),
        ("8.6", "sm_86"),
        ("7.5", "sm_75"),
        ("12.0", "sm_120"),  # multi-digit major
        ("", ""),  # empty
        ("9", ""),  # no dot / no minor
        ("x.0", ""),  # non-digit lead
        ("sm_90", ""),  # already a flag, not decimal input
    ],
)
def test_compute_capability_to_compiler_flag(compute_cap, expected):
    """Test conversion of decimal compute capability to the sm_XX compiler-flag form."""
    assert archspec.gpu.detect._compute_capability_to_compiler_flag(compute_cap) == expected


def test_nvidia_smi_info_parses_smi_output(monkeypatch):
    """Test that _nvidia_smi_info parses nvidia-smi CSV output into GPUMicroarch objects."""
    nvidia_smi_csv = (
        "NVIDIA GeForce RTX 5080, 595.58.03, 0x2C0210DE, 12.0\n"
        "NVIDIA H100 PCIe, 550.54.15, 0x233010DE, 9.0\n"
    )
    monkeypatch.setattr(archspec.gpu.detect.subprocess, "run", mock_smi(nvidia_smi_csv))

    gpus = archspec.gpu.detect._nvidia_smi_info()

    assert len(gpus) == 2
    assert all(gpu.vendor == "nvidia" for gpu in gpus)
    assert all(gpu.vendor_pci_code == "0x10de" for gpu in gpus)

    assert gpus[0].brand_string == "NVIDIA GeForce RTX 5080"
    assert gpus[0].driver_version == "595.58.03"
    assert gpus[0].component_pci_code == "0x2c02"
    assert gpus[0].compute_capability == "sm_120"
    assert gpus[0].name == "sm_120"

    assert gpus[1].brand_string == "NVIDIA H100 PCIe"
    assert gpus[1].driver_version == "550.54.15"
    assert gpus[1].component_pci_code == "0x2330"
    assert gpus[1].compute_capability == "sm_90"
    assert gpus[1].name == "sm_90"


# --- Stage 2: rocm-smi parsing ---


def test_rocm_smi_info_parses_rocm_smi_json(monkeypatch):
    """Test that _rocm_smi_info parses rocm-smi --json output into GPUMicroarch objects."""
    rocm_smi_json = json.dumps(
        {
            "card0": {"Card Series": "AMD Radeon RX 6800 XT", "Device ID": "0x73BF"},
            "card1": {"Market Name": "AMD Instinct MI250X", "GPU ID": "0x740C"},
            "system": {"Driver version": "6.7.0"},
        }
    )
    monkeypatch.setattr(archspec.gpu.detect.subprocess, "run", mock_smi(rocm_smi_json))

    gpus = archspec.gpu.detect._rocm_smi_info()

    assert len(gpus) == 2
    assert all(gpu.vendor == "amd" for gpu in gpus)
    assert all(gpu.vendor_pci_code == "0x1002" for gpu in gpus)
    assert all(gpu.driver_version == "6.7.0" for gpu in gpus)

    assert gpus[0].brand_string == "AMD Radeon RX 6800 XT"
    assert gpus[0].component_pci_code == "0x73bf"

    assert gpus[1].brand_string == "AMD Instinct MI250X"
    assert gpus[1].component_pci_code == "0x740c"


def test_rocm_smi_info_parses_real_mi300a_output(monkeypatch):
    """Test _rocm_smi_info against real rocm-smi output from a 4x MI300A machine."""
    rocm_smi_json = (
        '{"card0": {"Device Name": "AMD Instinct MI300A", "Device ID": "0x74a0", '
        '"Device Rev": "0x00", "Subsystem ID": "0x74a0", "GUID": "46363", '
        '"Card Series": "AMD Instinct MI300A", "Card Model": "0x74a0", '
        '"Card Vendor": "Advanced Micro Devices, Inc. [AMD/ATI]", "Card SKU": "N/A", '
        '"Node ID": "4", "GFX Version": "gfx942"}, '
        '"card1": {"Device Name": "AMD Instinct MI300A", "Device ID": "0x74a0", '
        '"Device Rev": "0x00", "Subsystem ID": "0x74a0", "GUID": "46186", '
        '"Card Series": "AMD Instinct MI300A", "Card Model": "0x74a0", '
        '"Card Vendor": "Advanced Micro Devices, Inc. [AMD/ATI]", "Card SKU": "N/A", '
        '"Node ID": "5", "GFX Version": "gfx942"}, '
        '"card2": {"Device Name": "AMD Instinct MI300A", "Device ID": "0x74a0", '
        '"Device Rev": "0x00", "Subsystem ID": "0x74a0", "GUID": "58426", '
        '"Card Series": "AMD Instinct MI300A", "Card Model": "0x74a0", '
        '"Card Vendor": "Advanced Micro Devices, Inc. [AMD/ATI]", "Card SKU": "N/A", '
        '"Node ID": "6", "GFX Version": "gfx942"}, '
        '"card3": {"Device Name": "AMD Instinct MI300A", "Device ID": "0x74a0", '
        '"Device Rev": "0x00", "Subsystem ID": "0x74a0", "GUID": "5131", '
        '"Card Series": "AMD Instinct MI300A", "Card Model": "0x74a0", '
        '"Card Vendor": "Advanced Micro Devices, Inc. [AMD/ATI]", "Card SKU": "N/A", '
        '"Node ID": "7", "GFX Version": "gfx942"}, '
        '"system": {"Driver version": "6.16.13"}}'
    )
    monkeypatch.setattr(archspec.gpu.detect.subprocess, "run", mock_smi(rocm_smi_json))

    gpus = archspec.gpu.detect._rocm_smi_info()

    assert len(gpus) == 4
    for gpu in gpus:
        assert gpu.vendor == "amd"
        assert gpu.vendor_pci_code == "0x1002"
        assert gpu.driver_version == "6.16.13"
        assert gpu.brand_string == "AMD Instinct MI300A"
        assert gpu.component_pci_code == "0x74a0"
        assert gpu.gfx_target == "gfx942"
        assert gpu.name == "gfx942"


def test_rocm_smi_info_handles_malformed_json(monkeypatch):
    """Test that _rocm_smi_info returns no GPUs when rocm-smi emits unparseable output."""
    monkeypatch.setattr(archspec.gpu.detect.subprocess, "run", mock_smi("not json"))

    assert archspec.gpu.detect._rocm_smi_info() == []


# --- Pipeline: host() merges SMI and sysfs sources ---


def test_host_detects_gpu_visible_only_to_smi(tmp_path, monkeypatch):
    """WSL case: a GPU absent from sysfs is still detected via an installed SMI tool."""
    monkeypatch.setattr(archspec.gpu.detect, "SYSFS_PCI_DEVICES", str(tmp_path))
    monkeypatch.setattr(archspec.gpu.detect.platform, "system", lambda: "Linux")
    monkeypatch.setattr(archspec.gpu.detect.shutil, "which", mock_which("nvidia-smi"))
    monkeypatch.setattr(
        archspec.gpu.detect.subprocess,
        "run",
        mock_smi("NVIDIA GeForce RTX 5080, 595.58.03, 0x2C0210DE\n"),
    )
    archspec.gpu.detect.host.cache_clear()

    gpus = archspec.gpu.detect.host()

    assert len(gpus) == 1
    assert gpus[0].vendor == "nvidia"
    assert gpus[0].driver_version == "595.58.03"


def test_host_keeps_sysfs_gpu_no_smi_describes(tmp_path, monkeypatch):
    """iGPU case: an AMD device sysfs sees but rocm-smi cannot is still reported,
    alongside the nvidia-smi-enriched NVIDIA card, without duplication."""
    make_pci_devices(
        tmp_path,
        [("0x030000", "0x10de", "0x2c02"), ("0x030000", "0x1002", "0x164e")],
    )
    monkeypatch.setattr(archspec.gpu.detect, "SYSFS_PCI_DEVICES", str(tmp_path))
    monkeypatch.setattr(archspec.gpu.detect.platform, "system", lambda: "Linux")
    monkeypatch.setattr(archspec.gpu.detect.shutil, "which", mock_which("nvidia-smi"))
    monkeypatch.setattr(
        archspec.gpu.detect.subprocess,
        "run",
        mock_smi("NVIDIA GeForce RTX 5080, 595.58.03, 0x2C0210DE\n"),
    )
    archspec.gpu.detect.host.cache_clear()

    gpus = archspec.gpu.detect.host()
    by_vendor = {g.vendor: g for g in gpus}

    assert len(gpus) == 2
    assert by_vendor["nvidia"].driver_version == "595.58.03"
    assert by_vendor["amd"].component_pci_code == "0x164e"
    assert by_vendor["amd"].driver_version == ""


def test_host_does_not_collapse_identical_gpus(tmp_path, monkeypatch):
    """Identical cards reported by an SMI tool are all kept, and sysfs duplicates of
    the same model do not double-count them."""
    make_pci_devices(
        tmp_path,
        [("0x030000", "0x10de", "0x2330"), ("0x030000", "0x10de", "0x2330")],
    )
    monkeypatch.setattr(archspec.gpu.detect, "SYSFS_PCI_DEVICES", str(tmp_path))
    monkeypatch.setattr(archspec.gpu.detect.platform, "system", lambda: "Linux")
    monkeypatch.setattr(archspec.gpu.detect.shutil, "which", mock_which("nvidia-smi"))
    monkeypatch.setattr(
        archspec.gpu.detect.subprocess,
        "run",
        mock_smi("NVIDIA H100, 550.54.15, 0x233010DE\nNVIDIA H100, 550.54.15, 0x233010DE\n"),
    )
    archspec.gpu.detect.host.cache_clear()

    gpus = archspec.gpu.detect.host()

    assert len(gpus) == 2
    assert all(g.brand_string == "NVIDIA H100" for g in gpus)
