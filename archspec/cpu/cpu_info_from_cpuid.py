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

from .cpuid import CPUID

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
    _, _, ecx, edx = cpuid(0x1)
    
    # Get the CPU flags
    flags = {
        "fpu": _is_bit_set(edx, 0),
        "vme": _is_bit_set(edx, 1),
        "de": _is_bit_set(edx, 2),
        "pse": _is_bit_set(edx, 3),
        "tsc": _is_bit_set(edx, 4),
        "msr": _is_bit_set(edx, 5),
        "pae": _is_bit_set(edx, 6),
        "mce": _is_bit_set(edx, 7),
        "cx8": _is_bit_set(edx, 8),
        "apic": _is_bit_set(edx, 9),
        #'reserved1' : _is_bit_set(edx, 10),
        "sep": _is_bit_set(edx, 11),
        "mtrr": _is_bit_set(edx, 12),
        "pge": _is_bit_set(edx, 13),
        "mca": _is_bit_set(edx, 14),
        "cmov": _is_bit_set(edx, 15),
        "pat": _is_bit_set(edx, 16),
        "pse36": _is_bit_set(edx, 17),
        "pn": _is_bit_set(edx, 18),
        "clflush": _is_bit_set(edx, 19),
        #'reserved2' : _is_bit_set(edx, 20),
        "dts": _is_bit_set(edx, 21),
        "acpi": _is_bit_set(edx, 22),
        "mmx": _is_bit_set(edx, 23),
        "fxsr": _is_bit_set(edx, 24),
        "sse": _is_bit_set(edx, 25),
        "sse2": _is_bit_set(edx, 26),
        "ss": _is_bit_set(edx, 27),
        "ht": _is_bit_set(edx, 28),
        "tm": _is_bit_set(edx, 29),
        "ia64": _is_bit_set(edx, 30),
        "pbe": _is_bit_set(edx, 31),
        "pni": _is_bit_set(ecx, 0),
        "pclmulqdq": _is_bit_set(ecx, 1),
        "dtes64": _is_bit_set(ecx, 2),
        "monitor": _is_bit_set(ecx, 3),
        "ds_cpl": _is_bit_set(ecx, 4),
        "vmx": _is_bit_set(ecx, 5),
        "smx": _is_bit_set(ecx, 6),
        "est": _is_bit_set(ecx, 7),
        "tm2": _is_bit_set(ecx, 8),
        "ssse3": _is_bit_set(ecx, 9),
        "cid": _is_bit_set(ecx, 10),
        #'reserved3' : _is_bit_set(ecx, 11),
        "fma": _is_bit_set(ecx, 12),
        "cx16": _is_bit_set(ecx, 13),
        "xtpr": _is_bit_set(ecx, 14),
        "pdcm": _is_bit_set(ecx, 15),
        #'reserved4' : _is_bit_set(ecx, 16),
        "pcid": _is_bit_set(ecx, 17),
        "dca": _is_bit_set(ecx, 18),
        "sse4_1": _is_bit_set(ecx, 19),
        "sse4_2": _is_bit_set(ecx, 20),
        "x2apic": _is_bit_set(ecx, 21),
        "movbe": _is_bit_set(ecx, 22),
        "popcnt": _is_bit_set(ecx, 23),
        "tscdeadline": _is_bit_set(ecx, 24),
        "aes": _is_bit_set(ecx, 25),
        "xsave": _is_bit_set(ecx, 26),
        "osxsave": _is_bit_set(ecx, 27),
        "avx": _is_bit_set(ecx, 28),
        "f16c": _is_bit_set(ecx, 29),
        "rdrnd": _is_bit_set(ecx, 30),
        "hypervisor": _is_bit_set(ecx, 31),
    }

    # Get a list of only the flags that are true
    flags = [k for k, v in flags.items() if v]

    # http://en.wikipedia.org/wiki/CPUID#EAX.3D7.2C_ECX.3D0:_Extended_Features
    if max_extension_support >= 7:
        _, ebx, ecx, _ = cpuid(7)

        # Get the extended CPU flags
        extended_flags = {
            #'fsgsbase' : _is_bit_set(ebx, 0),
            #'IA32_TSC_ADJUST' : _is_bit_set(ebx, 1),
            "sgx": _is_bit_set(ebx, 2),
            "bmi1": _is_bit_set(ebx, 3),
            "hle": _is_bit_set(ebx, 4),
            "avx2": _is_bit_set(ebx, 5),
            #'reserved' : _is_bit_set(ebx, 6),
            "smep": _is_bit_set(ebx, 7),
            "bmi2": _is_bit_set(ebx, 8),
            "erms": _is_bit_set(ebx, 9),
            "invpcid": _is_bit_set(ebx, 10),
            "rtm": _is_bit_set(ebx, 11),
            "pqm": _is_bit_set(ebx, 12),
            #'FPU CS and FPU DS deprecated' : _is_bit_set(ebx, 13),
            "mpx": _is_bit_set(ebx, 14),
            "pqe": _is_bit_set(ebx, 15),
            "avx512f": _is_bit_set(ebx, 16),
            "avx512dq": _is_bit_set(ebx, 17),
            "rdseed": _is_bit_set(ebx, 18),
            "adx": _is_bit_set(ebx, 19),
            "smap": _is_bit_set(ebx, 20),
            "avx512ifma": _is_bit_set(ebx, 21),
            "pcommit": _is_bit_set(ebx, 22),
            "clflushopt": _is_bit_set(ebx, 23),
            "clwb": _is_bit_set(ebx, 24),
            "intel_pt": _is_bit_set(ebx, 25),
            "avx512pf": _is_bit_set(ebx, 26),
            "avx512er": _is_bit_set(ebx, 27),
            "avx512cd": _is_bit_set(ebx, 28),
            "sha": _is_bit_set(ebx, 29),
            "avx512bw": _is_bit_set(ebx, 30),
            "avx512vl": _is_bit_set(ebx, 31),
            "prefetchwt1": _is_bit_set(ecx, 0),
            "avx512vbmi": _is_bit_set(ecx, 1),
            "umip": _is_bit_set(ecx, 2),
            "pku": _is_bit_set(ecx, 3),
            "ospke": _is_bit_set(ecx, 4),
            #'reserved' : _is_bit_set(ecx, 5),
            "avx512vbmi2": _is_bit_set(ecx, 6),
            #'reserved' : _is_bit_set(ecx, 7),
            "gfni": _is_bit_set(ecx, 8),
            "vaes": _is_bit_set(ecx, 9),
            "vpclmulqdq": _is_bit_set(ecx, 10),
            "avx512vnni": _is_bit_set(ecx, 11),
            "avx512bitalg": _is_bit_set(ecx, 12),
            #'reserved' : _is_bit_set(ecx, 13),
            "avx512vpopcntdq": _is_bit_set(ecx, 14),
            #'reserved' : _is_bit_set(ecx, 15),
            #'reserved' : _is_bit_set(ecx, 16),
            #'mpx0' : _is_bit_set(ecx, 17),
            #'mpx1' : _is_bit_set(ecx, 18),
            #'mpx2' : _is_bit_set(ecx, 19),
            #'mpx3' : _is_bit_set(ecx, 20),
            #'mpx4' : _is_bit_set(ecx, 21),
            "rdpid": _is_bit_set(ecx, 22),
            #'reserved' : _is_bit_set(ecx, 23),
            #'reserved' : _is_bit_set(ecx, 24),
            #'reserved' : _is_bit_set(ecx, 25),
            #'reserved' : _is_bit_set(ecx, 26),
            #'reserved' : _is_bit_set(ecx, 27),
            #'reserved' : _is_bit_set(ecx, 28),
            #'reserved' : _is_bit_set(ecx, 29),
            "sgx_lc": _is_bit_set(ecx, 30),
            #'reserved' : _is_bit_set(ecx, 31)
        }

        # Get a list of only the flags that are true
        extended_flags = [k for k, v in extended_flags.items() if v]
        flags += extended_flags

    # http://en.wikipedia.org/wiki/CPUID#EAX.3D80000001h:_Extended_Processor_Info_and_Feature_Bits
    if max_extension_support >= 0x80000001:
        _, ebc, ecx, _ = cpuid(0x80000001)

        # Get the extended CPU flags
        extended_flags = {
            "fpu": _is_bit_set(ebx, 0),
            "vme": _is_bit_set(ebx, 1),
            "de": _is_bit_set(ebx, 2),
            "pse": _is_bit_set(ebx, 3),
            "tsc": _is_bit_set(ebx, 4),
            "msr": _is_bit_set(ebx, 5),
            "pae": _is_bit_set(ebx, 6),
            "mce": _is_bit_set(ebx, 7),
            "cx8": _is_bit_set(ebx, 8),
            "apic": _is_bit_set(ebx, 9),
            #'reserved' : _is_bit_set(ebx, 10),
            "syscall": _is_bit_set(ebx, 11),
            "mtrr": _is_bit_set(ebx, 12),
            "pge": _is_bit_set(ebx, 13),
            "mca": _is_bit_set(ebx, 14),
            "cmov": _is_bit_set(ebx, 15),
            "pat": _is_bit_set(ebx, 16),
            "pse36": _is_bit_set(ebx, 17),
            #'reserved' : _is_bit_set(ebx, 18),
            "mp": _is_bit_set(ebx, 19),
            "nx": _is_bit_set(ebx, 20),
            #'reserved' : _is_bit_set(ebx, 21),
            "mmxext": _is_bit_set(ebx, 22),
            "mmx": _is_bit_set(ebx, 23),
            "fxsr": _is_bit_set(ebx, 24),
            "fxsr_opt": _is_bit_set(ebx, 25),
            "pdpe1gp": _is_bit_set(ebx, 26),
            "rdtscp": _is_bit_set(ebx, 27),
            #'reserved' : _is_bit_set(ebx, 28),
            "lm": _is_bit_set(ebx, 29),
            "3dnowext": _is_bit_set(ebx, 30),
            "3dnow": _is_bit_set(ebx, 31),
            "lahf_lm": _is_bit_set(ecx, 0),
            "cmp_legacy": _is_bit_set(ecx, 1),
            "svm": _is_bit_set(ecx, 2),
            "extapic": _is_bit_set(ecx, 3),
            "cr8_legacy": _is_bit_set(ecx, 4),
            "abm": _is_bit_set(ecx, 5),
            "sse4a": _is_bit_set(ecx, 6),
            "misalignsse": _is_bit_set(ecx, 7),
            "3dnowprefetch": _is_bit_set(ecx, 8),
            "osvw": _is_bit_set(ecx, 9),
            "ibs": _is_bit_set(ecx, 10),
            "xop": _is_bit_set(ecx, 11),
            "skinit": _is_bit_set(ecx, 12),
            "wdt": _is_bit_set(ecx, 13),
            #'reserved' : _is_bit_set(ecx, 14),
            "lwp": _is_bit_set(ecx, 15),
            "fma4": _is_bit_set(ecx, 16),
            "tce": _is_bit_set(ecx, 17),
            #'reserved' : _is_bit_set(ecx, 18),
            "nodeid_msr": _is_bit_set(ecx, 19),
            #'reserved' : _is_bit_set(ecx, 20),
            "tbm": _is_bit_set(ecx, 21),
            "topoext": _is_bit_set(ecx, 22),
            "perfctr_core": _is_bit_set(ecx, 23),
            "perfctr_nb": _is_bit_set(ecx, 24),
            #'reserved' : _is_bit_set(ecx, 25),
            "dbx": _is_bit_set(ecx, 26),
            "perftsc": _is_bit_set(ecx, 27),
            "pci_l2i": _is_bit_set(ecx, 28),
            #'reserved' : _is_bit_set(ecx, 29),
            #'reserved' : _is_bit_set(ecx, 30),
            #'reserved' : _is_bit_set(ecx, 31)
        }

        # Get a list of only the flags that are true
        extended_flags = [k for k, v in extended_flags.items() if v]
        flags += extended_flags

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

    cpuid = CPUID()

    # Get the cpu info from the CPUID register
    max_extension_support = get_max_extension_support(cpuid)
    info = get_info(cpuid)

    processor_brand = get_processor_brand(cpuid, max_extension_support)

    info = {
        "vendor_id_raw": get_vendor_id(cpuid),
        "brand_raw": processor_brand,
        "stepping": info["stepping"],
        "model": info["model"],
        "family": info["family"],
        "processor_type": info["processor_type"],
        "flags": get_flags(cpuid, max_extension_support),
    }
    return info
