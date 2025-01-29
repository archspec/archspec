# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""Detection of interconnect architectures"""
import collections
import functools
import os
import platform
import re
import subprocess
import warnings

import six

def detect_devices():
    """Detects the host interconnect and returns it."""
    interconnect_dict = {} 
    # check for network capable devices
    sys_class_net_path = "/sys/class/net/"
    if os.path.exists(sys_class_net_path): 
      network_devices = [f for f in os.listdir(sys_class_net_path)] 
      for device in network_devices:
        dev_state_fp = os.path.join(sys_class_net_path, device, "operstate")
        with open(dev_state_fp, 'r') as fp:
          device_state = fp.readline().strip()
          if device_state == "up":
            interconnect_dict.setdefault("ethernet", []).append(device)

    # check for infiniband capable devices
    sys_class_infiniband_path = "/sys/class/infiniband/"
    if os.path.exists(sys_class_infiniband_path): 
      infiniband_devices = [f for f in os.listdir(sys_class_infiniband_path)] 
      for device in infiniband_devices:
        dev_state_fp = os.path.join(sys_class_infiniband_path, device, "ports", "1", "state")
        with open(dev_state_fp, 'r') as fp:
          device_state = fp.readline().strip()
          if device_state == "4: ACTIVE":
            interconnect_dict.setdefault("infiniband", []).append(device)

    return (interconnect_dict)


def host():
    interconnect_dict = detect_devices()

    # prefer infiniband over tcp devices
    if "infiniband" in interconnect_dict:
      return ("infiniband_" + interconnect_dict["infiniband"][0])
    
    # fallback to ethernet devices
    if "ethernet" in interconnect_dict:
      return ("ethernet_" + interconnect_dict["ethernet"][0])

    # return empty if nothing found (should not happen)
    return ()


def raw_info_dictionary():
    interconnect_dict = detect_devices()

    return (interconnect_dict)
