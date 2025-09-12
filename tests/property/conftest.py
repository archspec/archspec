# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
from hypothesis import Verbosity, settings

settings.register_profile("ci", max_examples=1000, verbosity=Verbosity.verbose)
settings.load_profile("ci")
