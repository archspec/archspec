# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
from hypothesis import assume, given
from hypothesis import strategies as st

import archspec.cpu


def uarch():
    """Returns a strategy that generates a microarchitecture."""
    return st.sampled_from(list(archspec.cpu.TARGETS.values()))


@st.composite
def generic_and_specific(draw):
    """Returns a strategy that generates a pair of generic and specific microarchitectures."""
    hi = draw(uarch())
    assume(len(hi.ancestors) > 0)
    lo = draw(st.sampled_from(hi.ancestors))
    return lo, hi


@given(generic_and_specific())
def test_feature_subset_semantics(generic_specific_pair):
    """Tests that all features in a generic microarchitecture are also present in a more
    specific microarchitecture.
    """
    generic, specific = generic_specific_pair
    for feature in generic.features:
        assert feature in specific
