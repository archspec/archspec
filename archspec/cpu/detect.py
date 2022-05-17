# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""Detection of CPU microarchitectures"""
import collections
import functools
import os
import platform
import re
import subprocess
import warnings

import six

from .microarchitecture import generic_microarchitecture, TARGETS
from .schema import TARGETS_JSON

#: Mapping from operating systems to chain of commands
#: to obtain a dictionary of raw info on the current cpu
INFO_FACTORY = collections.defaultdict(list)

#: Mapping from micro-architecture families (x86_64, ppc64le, etc.) to
#: functions checking the compatibility of the host with a given target
COMPATIBILITY_CHECKS = {}


def info_dict(operating_system):
    """Decorator to mark functions that are meant to return raw info on
    the current cpu.

    Args:
        operating_system (str or tuple): operating system for which the marked
            function is a viable factory of raw info dictionaries.
    """

    def decorator(factory):
        INFO_FACTORY[operating_system].append(factory)

        @functools.wraps(factory)
        def _impl():
            info = factory()

            # Check that info contains a few mandatory fields
            msg = 'field "{0}" is missing from raw info dictionary'
            assert "vendor_id" in info, msg.format("vendor_id")
            assert "flags" in info, msg.format("flags")
            assert "model" in info, msg.format("model")
            assert "model_name" in info, msg.format("model_name")

            return info

        return _impl

    return decorator


@info_dict(operating_system="Linux")
def proc_cpuinfo():
    """Returns a raw info dictionary by parsing the first entry of
    ``/proc/cpuinfo``
    """
    info = {}
    with open("/proc/cpuinfo") as file:  # pylint: disable=unspecified-encoding
        for line in file:
            key, separator, value = line.partition(":")

            # If there's no separator and info was already populated
            # according to what's written here:
            #
            # http://www.linfo.org/proc_cpuinfo.html
            #
            # we are on a blank line separating two cpus. Exit early as
            # we want to read just the first entry in /proc/cpuinfo
            if separator != ":" and info:
                break

            info[key.strip()] = value.strip()
    return info


def _check_output(args, env):
    output = subprocess.Popen(  # pylint: disable=consider-using-with
        args, stdout=subprocess.PIPE, env=env
    ).communicate()[0]
    return six.text_type(output.decode("utf-8"))


def _machine():
    """ "Return the machine architecture we are on"""
    operating_system = platform.system()

    # If we are not on Darwin, trust what Python tells us
    if operating_system != "Darwin":
        return platform.machine()

    # On Darwin it might happen that we are on M1, but using an interpreter
    # built for x86_64. In that case "platform.machine() == 'x86_64'", so we
    # need to fix that.
    #
    # See: https://bugs.python.org/issue42704
    output = _check_output(
        ["sysctl", "-n", "machdep.cpu.brand_string"], env=_ensure_bin_usrbin_in_path()
    ).strip()

    if "Apple" in output:
        # Note that a native Python interpreter on Apple M1 would return
        # "arm64" instead of "aarch64". Here we normalize to the latter.
        return "aarch64"

    return "x86_64"


@info_dict(operating_system="Darwin")
def sysctl_info_dict():
    """Returns a raw info dictionary parsing the output of sysctl."""
    child_environment = _ensure_bin_usrbin_in_path()

    def sysctl(*args):
        return _check_output(["sysctl"] + list(args), env=child_environment).strip()

    if _machine() == "x86_64":
        flags = (
            sysctl("-n", "machdep.cpu.features").lower()
            + " "
            + sysctl("-n", "machdep.cpu.leaf7_features").lower()
        )
        info = {
            "vendor_id": sysctl("-n", "machdep.cpu.vendor"),
            "flags": flags,
            "model": sysctl("-n", "machdep.cpu.model"),
            "model name": sysctl("-n", "machdep.cpu.brand_string"),
        }
    else:
        model = (
            "m1" if "Apple" in sysctl("-n", "machdep.cpu.brand_string") else "unknown"
        )
        info = {
            "vendor_id": "Apple",
            "flags": [],
            "model": model,
            "CPU implementer": "Apple",
            "model name": sysctl("-n", "machdep.cpu.brand_string"),
        }
    return info


def _ensure_bin_usrbin_in_path():
    # Make sure that /sbin and /usr/sbin are in PATH as sysctl is
    # usually found there
    child_environment = dict(os.environ.items())
    search_paths = child_environment.get("PATH", "").split(os.pathsep)
    for additional_path in ("/sbin", "/usr/sbin"):
        if additional_path not in search_paths:
            search_paths.append(additional_path)
    child_environment["PATH"] = os.pathsep.join(search_paths)
    return child_environment


def adjust_raw_flags(info):
    """Adjust the flags detected on the system to homogenize
    slightly different representations.
    """
    # Flags detected on Darwin turned to their linux counterpart
    flags = info.get("flags", [])
    d2l = TARGETS_JSON["conversions"]["darwin_flags"]
    for darwin_flag, linux_flag in d2l.items():
        if darwin_flag in flags:
            info["flags"] += " " + linux_flag


def adjust_raw_vendor(info):
    """Adjust the vendor field to make it human readable"""
    if "CPU implementer" not in info:
        return

    # Mapping numeric codes to vendor (ARM). This list is a merge from
    # different sources:
    #
    # https://github.com/karelzak/util-linux/blob/master/sys-utils/lscpu-arm.c
    # https://developer.arm.com/docs/ddi0487/latest/arm-architecture-reference-manual-armv8-for-armv8-a-architecture-profile
    # https://github.com/gcc-mirror/gcc/blob/master/gcc/config/aarch64/aarch64-cores.def
    # https://patchwork.kernel.org/patch/10524949/
    arm_vendors = TARGETS_JSON["conversions"]["arm_vendors"]
    arm_code = info["CPU implementer"]
    if arm_code in arm_vendors:
        info["CPU implementer"] = arm_vendors[arm_code]


def raw_info_dictionary():
    """Returns a dictionary with information on the cpu of the current host.

    This function calls all the viable factories one after the other until
    there's one that is able to produce the requested information.
    """
    # pylint: disable=broad-except
    info = {}
    for factory in INFO_FACTORY[platform.system()]:
        try:
            info = factory()
        except Exception as exc:
            warnings.warn(str(exc))

        if info:
            adjust_raw_flags(info)
            adjust_raw_vendor(info)
            break

    return info


def compatible_microarchitectures(info):
    """Returns an unordered list of known micro-architectures that are
    compatible with the info dictionary passed as argument.

    Args:
        info (dict): dictionary containing information on the host cpu
    """
    architecture_family = _machine()
    # If a tester is not registered, be conservative and assume no known
    # target is compatible with the host
    tester = COMPATIBILITY_CHECKS.get(architecture_family, lambda x, y: False)
    return [x for x in TARGETS.values() if tester(info, x)] or [
        generic_microarchitecture(architecture_family)
    ]


def host():
    """Detects the host micro-architecture and returns it."""
    # Retrieve a dictionary with raw information on the host's cpu
    info = raw_info_dictionary()

    # Get a list of possible candidates for this micro-architecture
    candidates = compatible_microarchitectures(info)

    # Sorting criteria for candidates
    def sorting_fn(item):
        return len(item.ancestors), len(item.features)

    # Get the best generic micro-architecture
    generic_candidates = [c for c in candidates if c.vendor == "generic"]
    best_generic = max(generic_candidates, key=sorting_fn)

    # Filter the candidates to be descendant of the best generic candidate.
    # This is to avoid that the lack of a niche feature that can be disabled
    # from e.g. BIOS prevents detection of a reasonably performant architecture
    candidates = [c for c in candidates if c > best_generic]

    # If we don't have candidates, return the best generic micro-architecture
    if not candidates:
        return best_generic

    # Reverse sort of the depth for the inheritance tree among only targets we
    # can use. This gets the newest target we satisfy.
    return max(candidates, key=sorting_fn)


def compatibility_check(architecture_family):
    """Decorator to register a function as a proper compatibility check.

    A compatibility check function takes the raw info dictionary as a first
    argument and an arbitrary target as the second argument. It returns True
    if the target is compatible with the info dictionary, False otherwise.

    Args:
        architecture_family (str or tuple): architecture family for which
            this test can be used, e.g. x86_64 or ppc64le etc.
    """
    # Turn the argument into something iterable
    if isinstance(architecture_family, six.string_types):
        architecture_family = (architecture_family,)

    def decorator(func):
        COMPATIBILITY_CHECKS.update({family: func for family in architecture_family})
        return func

    return decorator


@compatibility_check(architecture_family=("ppc64le", "ppc64"))
def compatibility_check_for_power(info, target):
    """Compatibility check for PPC64 and PPC64LE architectures."""
    basename = platform.machine()
    generation_match = re.search(r"POWER(\d+)", info.get("cpu", ""))
    try:
        generation = int(generation_match.group(1))
    except AttributeError:
        # There might be no match under emulated environments. For instance
        # emulating a ppc64le with QEMU and Docker still reports the host
        # /proc/cpuinfo and not a Power
        generation = 0

    # We can use a target if it descends from our machine type and our
    # generation (9 for POWER9, etc) is at least its generation.
    arch_root = TARGETS[basename]
    return (
        target == arch_root or arch_root in target.ancestors
    ) and target.generation <= generation


@compatibility_check(architecture_family="x86_64")
def compatibility_check_for_x86_64(info, target):
    """Compatibility check for x86_64 architectures."""
    basename = "x86_64"
    vendor = info.get("vendor_id", "generic")
    features = set(info.get("flags", "").split())

    # We can use a target if it descends from our machine type, is from our
    # vendor, and we have all of its features
    arch_root = TARGETS[basename]
    return (
        (target == arch_root or arch_root in target.ancestors)
        and target.vendor in (vendor, "generic")
        and target.features.issubset(features)
    )


@compatibility_check(architecture_family="aarch64")
def compatibility_check_for_aarch64(info, target):
    """Compatibility check for AARCH64 architectures."""
    basename = "aarch64"
    features = set(info.get("Features", "").split())
    vendor = info.get("CPU implementer", "generic")

    arch_root = TARGETS[basename]
    return (
        (target == arch_root or arch_root in target.ancestors)
        and target.vendor in (vendor, "generic")
        # On macOS it seems impossible to get all the CPU features with syctl info
        and (target.features.issubset(features) or platform.system() == "Darwin")
    )


@compatibility_check(architecture_family="riscv64")
def compatibility_check_for_riscv64(info, target):
    """Compatibility check for riscv64 architectures."""
    basename = "riscv64"
    uarch = info.get("uarch")

    # sifive unmatched board
    if uarch == "sifive,u74-mc":
        uarch = "u74mc"
    # catch-all for unknown uarchs
    else:
        uarch = "riscv64"

    arch_root = TARGETS[basename]
    return (target == arch_root or arch_root in target.ancestors) and (
        target == uarch or target.vendor == "generic"
    )
