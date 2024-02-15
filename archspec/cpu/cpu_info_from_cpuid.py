#!/usr/bin/env python

# Extracted from py-cpuinfo and cpuid.py
# py-cpuinfo LICENSE:
#
# Copyright (c) 2014-2022 Matthew Brennan Jones <matthew.brennan.jones@gmail.com>
# Py-cpuinfo gets CPU info with pure Python
# It uses the MIT License
# It is hosted at: https://github.com/workhorsy/py-cpuinfo
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import platform
import re
import struct
import json
import os

from ..vendor.cpuid import cpuid as cpuid_mod


def _is_x86():
    arch_string_raw = platform.machine().lower()
    # X86
    if re.match(
        r"^i\d86$|^x86$|^x86_32$|^i86pc$|^ia32$|^ia-32$|^bepc$", arch_string_raw
    ):
        return True
    elif re.match(
        r"^x64$|^x86_64$|^x86_64t$|^i686-64$|^amd64$|^ia64$|^ia-64$", arch_string_raw
    ):
        return True

    return False

def _is_bit_set(reg, bit):
    mask = 1 << bit
    is_set = reg & mask > 0
    return is_set

def get_vendor_id(cpuid):
    _, ebx, ecx, edx = cpuid(0)
    return struct.pack("III", ebx, edx, ecx).decode("utf-8")

# http://en.wikipedia.org/wiki/CPUID#EAX.3D1:_Processor_Info_and_Feature_Bits
def get_info(cpuid):
    eax, _, _, _ = cpuid(1)

    # Get the CPU info
    stepping_id = (eax >> 0) & 0xF  # 4 bits
    model = (eax >> 4) & 0xF  # 4 bits
    family_id = (eax >> 8) & 0xF  # 4 bits
    processor_type = (eax >> 12) & 0x3  # 2 bits
    extended_model_id = (eax >> 16) & 0xF  # 4 bits
    extended_family_id = (eax >> 20) & 0xFF  # 8 bits
    family = 0

    if family_id in [15]:
        family = extended_family_id + family_id
    else:
        family = family_id

    if family_id in [6, 15]:
        model = (extended_model_id << 4) + model

    return {
        "stepping": stepping_id,
        "model": model,
        "family": family,
        "processor_type": processor_type,
    }


# http://en.wikipedia.org/wiki/CPUID#EAX.3D80000000h:_Get_Highest_Extended_Function_Supported
def get_max_extension_support(cpuid):
    # Check for extension support
    eax, _, _, _ = cpuid(0x80000000)
    return eax

# http://en.wikipedia.org/wiki/CPUID#EAX.3D1:_Processor_Info_and_Feature_Bits
def get_flags(cpuid, max_extension_support):
    flags = []
    regs = {}
    with open(os.path.join(os.path.dirname(__file__), "cpuid_flags.json")) as f:
        flags_json = json.load(f)

    for flag, v in flags_json.items():
        eax = v.pop("eax")

        if eax > max_extension_support:
            continue

        if eax not in regs:
            _, ebx, ecx, edx = cpuid(eax)
            regs[eax] = {
                "ebx": ebx,
                "ecx": ecx,
                "edx": edx,
            }

        reg, bit = v.popitem()
        if _is_bit_set(regs[eax][reg], bit):
            flags.append(flag)

    flags.sort()
    return flags

# http://en.wikipedia.org/wiki/CPUID#EAX.3D80000002h.2C80000003h.2C80000004h:_Processor_Brand_String
def get_processor_brand(cpuid, max_extension_support):
    name = "".join((struct.pack("IIII", *cpuid(0x80000000 + i)).decode("utf-8")
                for i in range(2, 5)))

    return name.split('\x00', 1)[0].strip()


def get_cpu_info_from_cpuid():
    """
    Returns the CPU info gathered by querying the X86 cpuid register in a new process.
    Returns {} on non X86 cpus.
    """

    from multiprocessing import Process, Queue

    # Return {} if this is not an X86 CPU
    if not _is_x86():
        return {}

    cpuid = cpuid_mod.CPUID()

    # Get the cpu info from the CPUID register
    max_extension_support = get_max_extension_support(cpuid)
    info = get_info(cpuid)

    processor_brand = get_processor_brand(cpuid, max_extension_support)

    info = {
        "vendor_id": get_vendor_id(cpuid),
        "model name": processor_brand,
        "model": info["model"],
        "cpu family": info["family"],
        "flags": " ".join(get_flags(cpuid, max_extension_support)),
    }
    return info
