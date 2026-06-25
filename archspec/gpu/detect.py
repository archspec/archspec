# Copyright 2019-2026 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""Detection of GPU microarchitectures"""

import collections
import functools
import json
import os
import platform
import shutil
import subprocess
import warnings
from typing import Callable, Dict, List, Tuple

from archspec.gpu.gpu_microarch import GPUMicroarch

# --- Constants and Detection Variables ---

#: PCI class codes for GPU devices
#: https://admin.pci-ids.ucw.cz/read/PD/03
GPU_PCI_CLASSES = ("0x030000", "0x030200", "0x120000")

#: Mapping from PCI vendor IDs to vendor names
#: https://devicehunt.com/view/type/pci/vendor/10DE -- NVIDIA
#: https://devicehunt.com/view/type/pci/vendor/1002 -- AMD
#: https://devicehunt.com/view/type/pci/vendor/8086 -- INTEL
GPU_VENDORS = {
    "0x10de": "nvidia",
    "0x1002": "amd",
    "0x8086": "intel",
}

#: Path to the sysfs PCI devices directory
SYSFS_PCI_DEVICES = "/sys/bus/pci/devices"

#: Mapping from operating systems to chain of commands
#: to obtain a list of raw info on the current gpus
INFO_FACTORY: Dict[str, List[Callable]] = collections.defaultdict(list)


# --- Decorator definitions ---


def detection(operating_system: str):
    """Decorator to mark functions that are meant to return raw information on detected GPUs.

    Args:
        operating_system: operating system where this function can be used.
    """

    def decorator(factory):
        INFO_FACTORY[operating_system].append(factory)
        return factory

    return decorator


# --- sysfs detection logic ---


def _read_sysfs_file(path: str) -> str:
    """Read and strip the contents of a sysfs file."""
    with open(path) as f:  # pylint: disable=unspecified-encoding
        return f.read().strip()


def _parse_nvidia_pci_device_id(combined_id: str) -> Tuple[str, str]:
    """Parse a combined PCI device ID into (device, vendor) codes.

    Args:
        combined_id: 10-character hex string from nvidia-smi ``pci.device_id``
            (e.g. ``0x2C0210DE``).

    Returns:
        A tuple of ``(component_pci_code, vendor_pci_code)`` in lowercase
        (e.g. ``("0x2c02", "0x10de")``).

    Raises:
        ValueError: if *combined_id* is not a valid 10-character hex string
            with a ``0x`` prefix.
    """
    if len(combined_id) != 10 or combined_id[:2] != "0x":
        raise ValueError(
            "invalid PCI device ID: expected 10-character '0x'-prefixed hex"
            f" string, got {combined_id!r}"
        )

    hex_digits = combined_id[2:]
    return (f"0x{hex_digits[:4]}".lower(), f"0x{hex_digits[4:]}".lower())


def _scan_sysfs_pci_for_gpus() -> List[GPUMicroarch]:
    """Enumerate GPUs by scanning sysfs PCI devices.

    Iterates over ``/sys/bus/pci/devices/`` and yields one entry per device whose
    PCI class indicates a GPU. Each entry carries only the identity available
    without a vendor tool: the vendor name and the PCI vendor and device codes.

    Returns:
        A list of GPUMicroarch, one per GPU-class PCI device on the system.
    """
    gpus: List[GPUMicroarch] = []

    if not os.path.isdir(SYSFS_PCI_DEVICES):
        return gpus

    for entry in os.listdir(SYSFS_PCI_DEVICES):
        device_dir = os.path.join(SYSFS_PCI_DEVICES, entry)
        if not os.path.isdir(device_dir):
            continue

        try:
            class_path = os.path.join(device_dir, "class")
            if not os.path.exists(class_path):
                continue
            if _read_sysfs_file(class_path) not in GPU_PCI_CLASSES:
                continue

            vendor_id = _read_sysfs_file(os.path.join(device_dir, "vendor"))
            vendor_name = GPU_VENDORS.get(vendor_id)
            if vendor_name is None:
                continue

            gpus.append(
                GPUMicroarch(
                    vendor=vendor_name,
                    vendor_pci_code=vendor_id,
                    component_pci_code=_read_sysfs_file(os.path.join(device_dir, "device")),
                )
            )
        except OSError as exc:
            warnings.warn(f"skipping PCI device {entry!r}: {exc}")

    return gpus


# --- nvidia-smi toolchain logic ---


#: Fields queried from nvidia-smi, in output-column order. ``compute_cap`` is
#: only recognized on newer drivers (~R495+); on older drivers it is dropped
#: (see ``_nvidia_smi_info``), so it is kept last to keep the leading columns
#: at stable indices regardless of whether it is present.
_NVIDIA_SMI_BASE_FIELDS = ["gpu_name", "driver_version", "pci.device_id"]


def _run_nvidia_smi(fields: List[str]) -> subprocess.CompletedProcess:
    """Run nvidia-smi querying the given GPU fields, in CSV format."""
    return subprocess.run(
        [
            "nvidia-smi",
            f"--query-gpu={','.join(fields)}",
            "--format=csv,noheader",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=True,
    )


def _nvidia_smi_info() -> List[GPUMicroarch]:
    """Retrieve info for all NVIDIA GPUs using nvidia-smi."""

    # Try query with compute_cap first, then fall back without it.
    fields = _NVIDIA_SMI_BASE_FIELDS + ["compute_cap"]
    try:
        result = _run_nvidia_smi(fields)
    except FileNotFoundError:
        warnings.warn("nvidia-smi is not installed; skipping NVIDIA GPU detection")
        return []
    except subprocess.CalledProcessError:
        # An unrecognized query field (compute_cap on older drivers, ~pre-R495)
        # fails the whole query, so retry with just the base fields rather than
        # losing detection entirely.
        fields = _NVIDIA_SMI_BASE_FIELDS
        try:
            result = _run_nvidia_smi(fields)
        except subprocess.CalledProcessError:
            return []

    gpus: List[GPUMicroarch] = []
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        # parts align positionally with `fields`:
        # [brand_string, driver_version, combined vendor+device pci code(, compute_cap)]
        if len(parts) < len(_NVIDIA_SMI_BASE_FIELDS):
            continue

        # Skip this gpu if id parsing is malformed
        try:
            pci_codes = _parse_nvidia_pci_device_id(parts[2])
        except ValueError as e:
            warnings.warn(f"skipping NVIDIA GPU: {e}")
            continue

        compute_capability = (
            _compute_capability_to_compiler_flag(parts[3]) if len(parts) > 3 else ""
        )
        gpus.append(
            GPUMicroarch(
                name=compute_capability,
                vendor="nvidia",
                brand_string=parts[0],
                driver_version=parts[1],
                component_pci_code=pci_codes[0],
                vendor_pci_code=pci_codes[1],
                compute_capability=compute_capability,
            )
        )
    return gpus


def _compute_capability_to_compiler_flag(name: str) -> str:
    """Transform decimal format compute capability to format expected by compiler flags.

    e.g. 9.0 -> sm_90
    """
    # validation
    if not name:
        return ""

    if not name[0].isdigit() or "." not in name:
        return ""

    # parsing
    parsed_name = name.replace(".", "")
    parsed_name = f"sm_{parsed_name}"

    return parsed_name


# --- rocm-smi toolchain logic ---


def _rocm_smi_info() -> List[GPUMicroarch]:
    """Retrieve info for all AMD GPUs using rocm-smi."""

    try:
        result = subprocess.run(
            [
                "rocm-smi",
                "--showproductname",
                "--showdriverversion",
                "--showid",
                "--json",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        )
    except FileNotFoundError:
        warnings.warn("rocm-smi is not installed; skipping AMD GPU detection")
        return []
    except subprocess.CalledProcessError:
        return []

    try:
        data = json.loads(result.stdout)
    except ValueError:
        return []

    # AMD's PCI vendor code is not reported by rocm-smi, so derive it from the
    # known vendor mapping the same way the ``vendor`` field is hardcoded.
    vendor_pci_code = next(code for code, name in GPU_VENDORS.items() if name == "amd")

    # The driver version is reported once for the whole system rather than
    # per-card, under a top-level "system" entry.
    system_info = data.get("system", {})
    driver_version = system_info.get("Driver version", "")

    gpus: List[GPUMicroarch] = []
    for key, info in data.items():
        if not key.startswith("card"):
            continue

        # Key names vary across rocm-smi versions, so fall back across the
        # known aliases for the marketing name and the PCI device ID.
        brand_string = info.get("Card Series") or info.get("Market Name") or ""
        component_pci_code = info.get("Device ID") or info.get("GPU ID") or ""
        gfx_version = info.get("GFX Version") or ""

        gpus.append(
            GPUMicroarch(
                name=gfx_version,
                vendor="amd",
                brand_string=brand_string,
                driver_version=driver_version,
                component_pci_code=component_pci_code.lower(),
                vendor_pci_code=vendor_pci_code,
                gfx_target=gfx_version,
            )
        )
    return gpus


# --- general smi logic ---


#: Vendor SMI tools used to enrich detection: (executable, info function).
_SMI_SOURCES: List[Tuple[str, Callable[[], List[GPUMicroarch]]]] = [
    ("nvidia-smi", _nvidia_smi_info),
    ("rocm-smi", _rocm_smi_info),
]


# --- final resolution logic ---


@detection(operating_system="Linux")
def _detect_gpus_linux() -> List[GPUMicroarch]:
    """Enumerate all GPUs present on Linux: vendor SMI tools plus a sysfs PCI scan fallback."""
    results: List[GPUMicroarch] = []

    for executable, info_fn in _SMI_SOURCES:
        if shutil.which(executable) is not None:
            results.extend(info_fn())

    described = {(gpu.vendor_pci_code, gpu.component_pci_code) for gpu in results}

    for gpu in _scan_sysfs_pci_for_gpus():
        if (gpu.vendor_pci_code, gpu.component_pci_code) not in described:
            results.append(gpu)

    return results


@functools.lru_cache(maxsize=None)
def host() -> List[GPUMicroarch]:
    """Detects the GPUs on the host system and returns information about them.

    Returns:
        A list of GPUMicroarch objects, one per detected GPU.
    """
    results: List[GPUMicroarch] = []

    for factory in INFO_FACTORY[platform.system()]:
        try:
            results = factory()
            break
        except Exception as e:  # pylint: disable=broad-except
            warnings.warn(str(e))

    return results
