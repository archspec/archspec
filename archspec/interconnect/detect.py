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

def host():
    """Detects the host interconnect and returns it."""
    interconnect_devices = [] 
    # check for network capable devices
    sys_class_net_path = "/sys/class/net/"
    if os.path.exists(sys_class_net_path): 
      network_devices = [f for f in os.listdir(sys_class_net_path)] 
      for device in network_devices:
        if os.path.exists(sys_class_net_path+device+"/operstate"): 
          f = open(sys_class_net_path+device+"/operstate",'r')
          device_state = f.readline().strip()
          if device_state == "up":
            interconnect_devices.append(device)
          f.close()

    # check for infiniband capable devices
    sys_class_infiniband_path = "/sys/class/infiniband/"
    if os.path.exists(sys_class_infiniband_path): 
      infiniband_devices = [f for f in os.listdir(sys_class_infiniband_path)] 
      print(infiniband_devices)

    return (interconnect_devices)

