# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""Tests for ranges of microarchitectures, and unions of them."""

import itertools

import pytest

import archspec.cpu
from archspec.cpu import (
    ArchspecError,
    InvalidRange,
    Microarchitecture,
    MicroarchitectureRange,
    MicroarchitectureRangeList,
    UnknownMicroarchitecture,
)

#: A selection of microarchitectures covering the interesting parts of both the ``x86_64`` DAG,
#: which is a lattice, and the ``aarch64`` one, which is not
SAMPLE_TARGET_NAMES = [
    # x86_64, including both sides of a bifurcation
    "x86_64",
    "x86_64_v2",
    "x86_64_v4",
    "broadwell",
    "mic_knl",
    "skylake",
    "cascadelake",
    "cannonlake",
    "icelake",
    "zen4",
    # aarch64, which is not a lattice
    "aarch64",
    "armv8.2a",
    "armv8.6a",
    "cortex_a72",
    "neoverse_n1",
    "ampere1",
    "ampere1a",
]

#: Unions with more than one member, including one crossing two architecture families
SAMPLE_LIST_STRINGS = [
    "x86_64_v2:,aarch64:",
    "broadwell:skylake,ampere1:",
    "mic_knl:,x86_64:mic_knl",
    "cascadelake:,cannonlake:",
]


def every_range():
    """Returns every valid range that can be built out of the known microarchitectures."""
    names = sorted(archspec.cpu.TARGETS)
    result = []
    for name in names:
        uarch = archspec.cpu.TARGETS[name]
        result.append(MicroarchitectureRange(lo=uarch))
        result.append(MicroarchitectureRange(hi=uarch))
    for lo_name, hi_name in itertools.combinations(names, 2):
        lo, hi = archspec.cpu.TARGETS[lo_name], archspec.cpu.TARGETS[hi_name]
        if lo <= hi:
            result.append(MicroarchitectureRange(lo=lo, hi=hi))
    return result


def every_sample_list():
    """Returns a selection of unions, covering the interesting parts of both the x86_64 and the
    aarch64 DAGs, including the empty one.
    """
    result = [MicroarchitectureRangeList()]
    for name in SAMPLE_TARGET_NAMES:
        uarch = archspec.cpu.TARGETS[name]
        result.append(MicroarchitectureRangeList([MicroarchitectureRange(lo=uarch)]))
        result.append(MicroarchitectureRangeList([MicroarchitectureRange(hi=uarch)]))

    result.extend(MicroarchitectureRangeList.from_string(x) for x in SAMPLE_LIST_STRINGS)
    return result


class TestMicroarchitectureRanges:
    @pytest.mark.parametrize(
        "lo,hi",
        [
            # lo > hi
            ("icelake", "broadwell"),
            # Different families
            ("x86_64", "neoverse_n1"),
            # Not comparable
            ("broadwell", "zen4"),
        ],
    )
    def test_errors_in_construction(self, lo, hi):
        """Tests that constructing a range with inconsistent boundaries raises InvalidRange."""
        lo, hi = archspec.cpu.TARGETS[lo], archspec.cpu.TARGETS[hi]
        with pytest.raises(InvalidRange, match="is not compatible with"):
            MicroarchitectureRange(lo=lo, hi=hi)

    @pytest.mark.parametrize(
        "lo,hi,item,expected",
        [
            # The key is one of the boundaries
            ("broadwell", "skylake", "broadwell", True),
            ("broadwell", None, "broadwell", True),
            ("broadwell", "skylake", "skylake", True),
            (None, "skylake", "skylake", True),
            # Key is in the middle of the boundary
            ("x86_64_v2", "skylake", "broadwell", True),
            ("x86_64_v2", None, "broadwell", True),
            (None, "skylake", "broadwell", True),
            # Key is not in the range
            ("broadwell", "skylake", "bulldozer", False),
            ("broadwell", None, "bulldozer", False),
            (None, "skylake", "bulldozer", False),
            # Bifurcations in the microarchitectures DAG
            ("broadwell", "cascadelake", "cannonlake", False),
            ("broadwell", "cannonlake", "cascadelake", False),
        ],
    )
    def test_range_contains(self, lo, hi, item, expected):
        """Tests that a range holds exactly the microarchitectures between its boundaries."""
        uarch_range = MicroarchitectureRange(lo=lo, hi=hi)
        assert (item in uarch_range) is expected
        assert (Microarchitecture.from_string(item) in uarch_range) is expected

    @pytest.mark.parametrize(
        "r1_args,r2_args,expected",
        [
            # A closed range inside an open one
            (("broadwell", "icelake"), ("x86_64_v2", None), True),
            # A closed range inside a wider closed one
            (("broadwell", "skylake"), ("x86_64", "icelake"), True),
            # Same boundaries, so each contains the other
            (("broadwell", "skylake"), ("broadwell", "skylake"), True),
            # An open range is never inside a closed one, even when they enumerate the same
            # microarchitectures today
            (("mic_knl", None), ("mic_knl", "mic_knl"), False),
            # Nested open ranges
            (("zen4", None), ("x86_64_v2", None), True),
            (("x86_64_v2", None), ("zen4", None), False),
            # Ranges from different families are never contained in one another
            (("broadwell", "skylake"), ("aarch64", None), False),
        ],
    )
    def test_range_containment(self, r1_args, r2_args, expected):
        """Tests that the comparison operators between ranges implement subset semantics."""
        r1 = MicroarchitectureRange(lo=r1_args[0], hi=r1_args[1])
        r2 = MicroarchitectureRange(lo=r2_args[0], hi=r2_args[1])

        assert (r1 <= r2) is expected
        assert (r2 >= r1) is expected
        # The strict operators agree, except when the two ranges are equal
        assert (r1 < r2) is (expected and r1 != r2)
        assert (r2 > r1) is (expected and r1 != r2)

    @pytest.mark.parametrize(
        "r1_args,r2_args",
        [
            # Overlapping, but neither is inside the other
            (("broadwell", "icelake"), ("x86_64", "skylake")),
            # Disjoint branches of the same bifurcation
            (("cannonlake", None), ("cascadelake", None)),
        ],
    )
    def test_containment_of_incomparable_ranges(self, r1_args, r2_args):
        """Tests that containment is a partial order, so two ranges can be incomparable."""
        r1 = MicroarchitectureRange(lo=r1_args[0], hi=r1_args[1])
        r2 = MicroarchitectureRange(lo=r2_args[0], hi=r2_args[1])

        assert not r1 <= r2
        assert not r2 <= r1
        assert r1 != r2

    @pytest.mark.parametrize(
        "range_str,expected_str",
        [
            # Closed ranges
            ("broadwell:skylake", "broadwell:skylake"),
            ("  broadwell : skylake  ", "broadwell:skylake"),
            # Ranges that are unbounded above
            ("broadwell:", "broadwell:"),
            # A missing lower boundary is normalized to the family of the upper one
            (":skylake", "x86_64:skylake"),
            (":neoverse_n1", "aarch64:neoverse_n1"),
            # A bare name is the range holding that microarchitecture only, and is rendered
            # back as a bare name
            ("broadwell", "broadwell"),
            ("broadwell:broadwell", "broadwell"),
        ],
    )
    def test_range_from_string(self, range_str, expected_str):
        """Tests that a range can be parsed from its string representation, and that a missing
        lower boundary is normalized to the family of the upper one.
        """
        assert str(MicroarchitectureRange.from_string(range_str)) == expected_str

    @pytest.mark.parametrize(
        "range_str,exception",
        [
            # Too many boundaries
            ("broadwell:skylake:icelake", InvalidRange),
            # Unknown microarchitecture names
            ("broadwell:not_a_target", ValueError),
            ("not_a_target:", ValueError),
            ("not_a_target", ValueError),
            # Reversed boundaries
            ("skylake:broadwell", InvalidRange),
            # Boundaries from different families
            ("x86_64:neoverse_n1", InvalidRange),
            # Neither the empty set nor the set of every microarchitecture is a range
            ("{}", InvalidRange),
            (":", InvalidRange),
        ],
    )
    def test_range_from_string_errors(self, range_str, exception):
        """Tests that parsing an invalid range from a string raises."""
        with pytest.raises(exception):
            MicroarchitectureRange.from_string(range_str)

    def test_iteration_is_deterministic_and_topological(self):
        """Tests that iterating a range yields a stable order, with ancestors always coming
        before their descendants.
        """
        uarch_range = MicroarchitectureRange(lo="x86_64_v2", hi="haswell")
        result = list(uarch_range)

        assert result == list(uarch_range), "iteration order is not stable"
        assert len(result) == len(uarch_range)
        for index, uarch in enumerate(result):
            descendants_before = [x for x in result[:index] if uarch < x]
            assert not descendants_before, f"{uarch} comes after its descendants"

    @pytest.mark.parametrize("item", [42, None, 3.14])
    def test_contains_rejects_invalid_types(self, item):
        """Tests that testing membership of an object that is not a microarchitecture, nor a
        string, raises a TypeError.
        """
        uarch_range = MicroarchitectureRange(lo="broadwell", hi="icelake")
        with pytest.raises(TypeError, match="only objects of string or Microarchitecture types"):
            item in uarch_range  # pylint: disable=pointless-statement

    @pytest.fixture(scope="class")
    def all_ranges(self):
        """Every valid range that can be built out of the known microarchitectures."""
        return every_range()

    @pytest.fixture(scope="class")
    def sample_ranges(self):
        """A smaller selection of ranges, covering the interesting parts of both the x86_64 and
        the aarch64 DAGs, for the properties that need to compare ranges pairwise.
        """
        result = []
        for name in SAMPLE_TARGET_NAMES:
            uarch = archspec.cpu.TARGETS[name]
            result.append(MicroarchitectureRange(lo=uarch))
            result.append(MicroarchitectureRange(hi=uarch))
        return result

    def test_contains_agrees_with_the_partial_order(self, all_ranges):
        """Tests that membership in a range agrees with the partial order on its boundaries, for
        every range and every known microarchitecture.
        """
        for uarch_range in all_ranges:
            for uarch in archspec.cpu.TARGETS.values():
                expected = uarch_range.lo <= uarch and (
                    uarch_range.hi is None or uarch <= uarch_range.hi
                )
                assert (uarch in uarch_range) is expected

    def test_range_equality_agrees_with_hashing(self, all_ranges):
        """Tests that equal ranges hash equally and share the same string representation, so that
        ranges can be used in sets and as dictionary keys.
        """
        for r1, r2 in itertools.combinations(all_ranges, 2):
            if r1 == r2:
                assert hash(r1) == hash(r2)
                assert str(r1) == str(r2)
            else:
                assert str(r1) != str(r2)

        # The string representation is a faithful encoding, so it cannot collapse distinct ranges
        assert len({str(x) for x in all_ranges}) == len(set(all_ranges))

    def test_string_representation_round_trips(self, all_ranges):
        """Tests that every range can be recovered from its string representation."""
        for uarch_range in all_ranges:
            assert MicroarchitectureRange.from_string(str(uarch_range)) == uarch_range

    def test_containment_is_a_partial_order(self, sample_ranges):
        """Tests that containment between ranges is reflexive, antisymmetric and transitive."""
        for uarch_range in sample_ranges:
            assert uarch_range <= uarch_range

        for r1, r2 in itertools.permutations(sample_ranges, 2):
            if r1 <= r2 and r2 <= r1:
                assert r1 == r2

        for r1, r2, r3 in itertools.permutations(sample_ranges, 3):
            if r1 <= r2 and r2 <= r3:
                assert r1 <= r3

    def test_containment_agrees_with_the_microarchitectures_in_range(self, sample_ranges):
        """Tests that when a range contains another, it also contains all of its
        microarchitectures.
        """
        for r1, r2 in itertools.permutations(sample_ranges, 2):
            if r1 <= r2:
                assert all(x in r2 for x in r1)

    def test_a_range_supports_neither_union_nor_intersection(self):
        """Tests that a single range offers neither ``|`` nor ``&``.

        A range is closed under neither operation, since the microarchitecture partial order is
        not a lattice. Both live on MicroarchitectureRangeList, where they can be total, rather
        than being offered here in a form that fails on some inputs.
        """
        r1 = MicroarchitectureRange.from_string("armv8.6a:")
        r2 = MicroarchitectureRange.from_string("neoverse_n1:")

        with pytest.raises(TypeError, match="unsupported operand"):
            r1 & r2  # pylint: disable=pointless-statement
        with pytest.raises(TypeError, match="unsupported operand"):
            r1 | r2  # pylint: disable=pointless-statement


#: Pairs of ranges whose intersection has no unique boundary, so that it cannot be expressed as a
#: single range. They all come from the ``aarch64`` family, where ``ampere1``/``ampere1a`` and the
#: ``neoverse`` chips have two parents each.
AMBIGUOUS_RANGE_PAIRS = list(
    itertools.product(
        ["armv8.3a:", "armv8.4a:", "armv8.5a:", "armv8.6a:", "armv9.0a:"],
        ["cortex_a72:", "neoverse_n1:"],
    )
) + list(
    itertools.combinations(
        [":ampere1", ":ampere1a", ":neoverse_n2", ":neoverse_v1", ":neoverse_v2"], 2
    )
)


class TestMicroarchitectureRangeLists:
    @pytest.fixture(scope="class")
    def sample_lists(self):
        """A selection of unions, covering the interesting parts of both the x86_64 and the
        aarch64 DAGs, for the properties that need to compare unions pairwise.
        """
        return every_sample_list()

    @pytest.mark.parametrize(
        "list_str,expected_str",
        [
            # A single range, in each of its forms
            ("broadwell:skylake", "broadwell:skylake"),
            ("broadwell:", "broadwell:"),
            (":skylake", "x86_64:skylake"),
            ("broadwell", "broadwell"),
            # Members are sorted, so that the representation is stable
            ("zen4:,broadwell:", "broadwell:,zen4:"),
            ("  broadwell : skylake , zen4 ", "broadwell:skylake,zen4"),
            # Members from different architecture families can be joined
            ("x86_64,aarch64", "aarch64,x86_64"),
            # Duplicates and members contained in another member are dropped
            ("broadwell:,broadwell:", "broadwell:"),
            ("x86_64:,broadwell:skylake", "x86_64:"),
            ("broadwell:skylake,x86_64:", "x86_64:"),
            ("skylake,broadwell:icelake", "broadwell:icelake"),
        ],
    )
    def test_list_from_string(self, list_str, expected_str):
        """Tests that a union can be parsed from its string representation, and that it is
        normalized on construction.
        """
        assert str(MicroarchitectureRangeList.from_string(list_str)) == expected_str

    @pytest.mark.parametrize(
        "list_str,exception",
        [
            ("broadwell:skylake:icelake,zen4:", InvalidRange),
            ("broadwell:,not_a_target", ValueError),
            ("broadwell:,", ValueError),
            # The empty set has no string representation
            ("{}", InvalidRange),
            ("{},broadwell:", InvalidRange),
            # ':' is a shorthand for every microarchitecture, and only as the whole string
            (":,broadwell:", InvalidRange),
        ],
    )
    def test_list_from_string_errors(self, list_str, exception):
        """Tests that parsing an invalid union from a string raises."""
        with pytest.raises(exception):
            MicroarchitectureRangeList.from_string(list_str)

    def test_empty_list(self):
        """Tests the properties of the union with no members."""
        empty = MicroarchitectureRangeList()

        assert empty.empty is True
        assert empty.ranges == ()
        assert len(empty) == 0
        assert list(empty) == []
        assert "broadwell" not in empty
        assert str(empty) == "{}"

    def test_list_contains(self):
        """Tests that a union holds the microarchitectures of all its members, and nothing
        else.
        """
        uarch_list = MicroarchitectureRangeList.from_string("broadwell:skylake,neoverse_n1:")

        assert "broadwell" in uarch_list
        assert "skylake" in uarch_list
        assert "neoverse_n1" in uarch_list
        assert "ampere1" in uarch_list
        assert archspec.cpu.TARGETS["skylake"] in uarch_list
        assert "haswell" not in uarch_list
        assert "icelake" not in uarch_list
        assert "cortex_a72" not in uarch_list

    @pytest.mark.parametrize("item", [42, None, 3.14])
    def test_list_contains_rejects_invalid_types(self, item):
        """Tests that testing membership of an object that is not a microarchitecture, nor a
        string, raises a TypeError, even when the union is empty.
        """
        for uarch_list in (
            MicroarchitectureRangeList.from_string("broadwell:icelake"),
            MicroarchitectureRangeList(),
        ):
            with pytest.raises(TypeError, match="only objects of string or Microarchitecture"):
                item in uarch_list  # pylint: disable=pointless-statement

    def test_list_iteration_is_deterministic_and_topological(self):
        """Tests that iterating a union yields each microarchitecture once, in a stable order
        with ancestors always coming before their descendants.
        """
        # The two members overlap, so a microarchitecture must not be yielded twice
        uarch_list = MicroarchitectureRangeList.from_string("x86_64:skylake,broadwell:icelake")
        result = list(uarch_list)

        assert result == list(uarch_list), "iteration order is not stable"
        assert len(result) == len(uarch_list) == len(set(result))
        assert set(result) == set(MicroarchitectureRange(lo="x86_64", hi="skylake")) | set(
            MicroarchitectureRange(lo="broadwell", hi="icelake")
        )
        for index, uarch in enumerate(result):
            descendants_before = [x for x in result[:index] if uarch < x]
            assert not descendants_before, f"{uarch} comes after its descendants"

    @pytest.mark.parametrize(
        "l1_str,l2_str,expected_str",
        [
            # The four shapes where a single range cannot express the intersection
            ("armv9.0a:", "neoverse_n1:", "neoverse_n2:,neoverse_v2:"),
            ("armv8.6a:", "neoverse_n1:", "ampere1:,ampere1a:"),
            (":ampere1", ":ampere1a", "aarch64:armv8.6a,aarch64:neoverse_n1"),
            (":neoverse_n2", ":neoverse_v2", "aarch64:armv9.0a,aarch64:neoverse_n1"),
            # Intersections that a single range does express
            ("skylake:icelake", "x86_64_v2:cascadelake", "skylake:cascadelake"),
            ("x86_64:skylake", "skylake:icelake", "skylake"),
            (":cascadelake", ":cannonlake", "x86_64:skylake"),
            ("x86_64_v2:icelake", ":zen2", "x86_64_v2:x86_64_v3"),
            # One boundary open on each side
            ("broadwell:", ":cascadelake", "broadwell:cascadelake"),
            # Both unbounded above, so the result stays open
            ("x86_64_v2:", "x86_64_v3:", "x86_64_v3:"),
            ("x86_64_v2:", "zen4:", "zen4:"),
            # Collapsing to a single microarchitecture
            ("broadwell", "broadwell", "broadwell"),
            ("armv8.6a:", "neoverse_n1:ampere1", "ampere1"),
            # Different families give the empty union rather than raising
            ("broadwell:icelake", "aarch64:", "{}"),
            ("broadwell:", ":neoverse_n1", "{}"),
            # Intersections of unions with more than one member
            ("x86_64:,aarch64:", "broadwell:,neoverse_n1:", "broadwell:,neoverse_n1:"),
            ("x86_64:broadwell,zen4:", "aarch64:", "{}"),
        ],
    )
    def test_list_intersection(self, l1_str, l2_str, expected_str):
        """Tests that intersecting two unions gives the expected union, and that it commutes."""
        l1 = MicroarchitectureRangeList.from_string(l1_str)
        l2 = MicroarchitectureRangeList.from_string(l2_str)
        # The empty set has no string representation, so the table above spells it with the
        # display form that "str" produces for it
        expected = (
            MicroarchitectureRangeList()
            if expected_str == "{}"
            else MicroarchitectureRangeList.from_string(expected_str)
        )

        assert l1 & l2 == expected
        assert l2 & l1 == expected
        assert str(l1 & l2) == expected_str

    @pytest.mark.parametrize("r1_str,r2_str", AMBIGUOUS_RANGE_PAIRS)
    def test_list_intersection_is_total(self, r1_str, r2_str):
        """Tests that the intersection of two unions never raises, even for the pairs of ranges
        whose intersection has no unique boundary, and that it is the exact set intersection.
        """
        l1 = MicroarchitectureRangeList.from_string(r1_str)
        l2 = MicroarchitectureRangeList.from_string(r2_str)
        intersection = l1 & l2

        assert len(intersection.ranges) > 1, "an ambiguous boundary needs more than one range"
        assert set(intersection) == set(l1) & set(l2)
        assert intersection <= l1
        assert intersection <= l2

    def test_list_intersection_keeps_one_member_when_boundaries_are_unique(self, sample_lists):
        """Tests that a union grows extra members only when it has to.

        Whenever the intersection of two single ranges has unique boundaries, the result is that
        one range, so the number of members does not creep up on the common case.
        """
        ranges = [x for uarch_list in sample_lists for x in uarch_list.ranges]
        multi_member = 0
        for r1, r2 in itertools.combinations(ranges, 2):
            intersection = MicroarchitectureRangeList([r1]) & MicroarchitectureRangeList([r2])
            assert set(intersection) == set(r1) & set(r2)
            if len(intersection.ranges) > 1:
                multi_member += 1
                # Only same family pairs can need more than one member
                assert r1.family == r2.family
        assert multi_member, "no pair needed more than one member"

    def test_list_intersection_is_the_exact_set_intersection(self, sample_lists):
        """Tests that the intersection of two unions holds exactly the microarchitectures that
        belong to both of them, and is contained in each of them.
        """
        for l1, l2 in itertools.combinations(sample_lists, 2):
            intersection = l1 & l2
            assert set(intersection) == set(l1) & set(l2)
            assert intersection <= l1
            assert intersection <= l2

    def test_list_intersection_algebraic_laws(self, sample_lists):
        """Tests that intersection is idempotent, commutative, and that the empty union absorbs
        any other union.
        """
        empty = MicroarchitectureRangeList()
        for uarch_list in sample_lists:
            assert uarch_list & uarch_list == uarch_list
            assert uarch_list & empty == empty
            assert empty & uarch_list == empty

        for l1, l2 in itertools.combinations(sample_lists, 2):
            assert l1 & l2 == l2 & l1

    def test_list_intersection_is_associative(self, sample_lists):
        """Tests that intersection is associative. Unlike the single range case this needs no
        exception handling, since the operation is total.
        """
        for l1, l2, l3 in itertools.combinations(sample_lists, 3):
            assert (l1 & l2) & l3 == l1 & (l2 & l3)

    def test_list_intersection_rejects_invalid_types(self):
        """Tests that a union can only be intersected with another union."""
        uarch_list = MicroarchitectureRangeList.from_string("broadwell:")
        with pytest.raises(TypeError):
            uarch_list & MicroarchitectureRange.from_string("broadwell:")

    @pytest.mark.parametrize(
        "l1_str,l2_str,expected",
        [
            # A single member inside a single member
            ("broadwell:icelake", "x86_64_v2:", True),
            ("x86_64_v2:", "broadwell:icelake", False),
            # Every member is inside a member of the other union
            ("broadwell:,neoverse_n1:", "x86_64:,aarch64:", True),
            ("x86_64:,aarch64:", "broadwell:,neoverse_n1:", False),
            # One member is inside, the other is not
            ("broadwell:,neoverse_n1:", "x86_64:", False),
            ("broadwell:", "x86_64:,aarch64:", True),
            # A union always contains itself
            ("broadwell:,neoverse_n1:", "broadwell:,neoverse_n1:", True),
        ],
    )
    def test_list_containment(self, l1_str, l2_str, expected):
        """Tests that the comparison operators between unions implement subset semantics."""
        l1 = MicroarchitectureRangeList.from_string(l1_str)
        l2 = MicroarchitectureRangeList.from_string(l2_str)

        assert (l1 <= l2) is expected
        assert (l2 >= l1) is expected
        # The strict operators agree, except when the two unions are equal
        assert (l1 < l2) is (expected and l1 != l2)
        assert (l2 > l1) is (expected and l1 != l2)

    def test_list_containment_is_a_partial_order(self, sample_lists):
        """Tests that containment between unions is reflexive, antisymmetric and transitive."""
        for uarch_list in sample_lists:
            assert uarch_list <= uarch_list

        for l1, l2 in itertools.permutations(sample_lists, 2):
            if l1 <= l2 and l2 <= l1:
                assert l1 == l2

        for l1, l2, l3 in itertools.permutations(sample_lists, 3):
            if l1 <= l2 and l2 <= l3:
                assert l1 <= l3

    def test_list_containment_is_sound(self, sample_lists):
        """Tests that containment between unions is never claimed when the microarchitectures of
        one are not a subset of the microarchitectures of the other.

        Containment is checked member-wise, which is sufficient but not necessary, so the
        converse does not hold, see ``test_list_containment_is_conservative``.
        """
        for l1, l2 in itertools.permutations(sample_lists, 2):
            if l1 <= l2:
                assert set(l1) <= set(l2)
                assert all(x in l2 for x in l1)

    def test_list_containment_is_conservative(self):
        """Tests the documented approximation in containment: a member covered by two members of
        the other union, rather than by a single one, is not recognized.
        """
        narrow = MicroarchitectureRangeList.from_string("x86_64:icelake")
        wide = MicroarchitectureRangeList.from_string("x86_64:cascadelake,cannonlake:icelake")

        assert set(narrow) <= set(wide)
        assert not narrow <= wide

    def test_list_equality_agrees_with_hashing(self, sample_lists):
        """Tests that equal unions hash equally and share the same string representation, so
        that unions can be used in sets and as dictionary keys.
        """
        for l1, l2 in itertools.combinations(sample_lists, 2):
            if l1 == l2:
                assert hash(l1) == hash(l2)
                assert str(l1) == str(l2)
            else:
                assert str(l1) != str(l2)

        # The string representation is a faithful encoding, so it cannot collapse distinct unions
        assert len({str(x) for x in sample_lists}) == len(set(sample_lists))

    def test_list_string_representation_round_trips(self, sample_lists):
        """Tests that every union can be recovered from its string representation."""
        extra = [
            # A union of point ranges, which render as bare names
            MicroarchitectureRangeList.from_string("broadwell,zen4"),
            # A single member union, with each kind of boundary
            MicroarchitectureRangeList.from_string("broadwell"),
            MicroarchitectureRangeList.from_string("broadwell:"),
            MicroarchitectureRangeList.from_string(":broadwell"),
            MicroarchitectureRangeList.from_string("x86_64:broadwell"),
        ]
        # The empty union is the one value that does not round-trip, since the empty set is
        # deliberately not part of the string grammar
        candidates = [x for x in list(sample_lists) + extra if not x.empty]
        assert len(candidates) == len(sample_lists) + len(extra) - 1
        for uarch_list in candidates:
            assert MicroarchitectureRangeList.from_string(str(uarch_list)) == uarch_list

    def test_list_repr(self):
        """Tests that the repr of a union shows its members."""
        uarch_list = MicroarchitectureRangeList.from_string("broadwell:skylake")
        assert repr(uarch_list) == (
            "MicroarchitectureRangeList([MicroarchitectureRange("
            "lo=Microarchitecture('broadwell'), hi=Microarchitecture('skylake'))])"
        )


class TestConcreteMicroarchitectures:
    """Tests recovering a single microarchitecture from a range or a union of ranges."""

    @pytest.mark.parametrize(
        "range_str,expected",
        [
            # A bare name is the range holding that microarchitecture only
            ("broadwell", "broadwell"),
            ("broadwell:broadwell", "broadwell"),
            (":x86_64", "x86_64"),
            # Ranges spanning more than one microarchitecture are not concrete
            ("broadwell:skylake", None),
            ("broadwell:", None),
            (":skylake", None),
            # An open range with a single member today is still not concrete, since a
            # descendant added to the database in the future would fall in it
            ("mic_knl:", None),
        ],
    )
    def test_range_concrete(self, range_str, expected):
        """Tests that a range is concrete exactly when its boundaries are the same
        microarchitecture, which is a property of the boundaries and not of the database.
        """
        result = MicroarchitectureRange.from_string(range_str).concrete
        if expected is None:
            assert result is None
        else:
            assert result is archspec.cpu.TARGETS[expected]

    @pytest.mark.parametrize(
        "list_str,expected",
        [
            ("broadwell", "broadwell"),
            ("broadwell:broadwell", "broadwell"),
            # More than one member is never concrete, even when every member is
            ("broadwell,zen4", None),
            # A single member that is not concrete
            ("broadwell:skylake", None),
            ("mic_knl:", None),
        ],
    )
    def test_list_concrete(self, list_str, expected):
        """Tests that a union is concrete exactly when it has one concrete member."""
        result = MicroarchitectureRangeList.from_string(list_str).concrete
        if expected is None:
            assert result is None
        else:
            assert result is archspec.cpu.TARGETS[expected]

    def test_concrete_is_not_the_same_question_as_length(self):
        """Tests the case that motivates having ``concrete`` at all: ``len() == 1`` is true both
        for a genuinely concrete range and for an open range that happens to hold one
        microarchitecture today, and the two must not be conflated.
        """
        concrete = MicroarchitectureRangeList.from_string("mic_knl")
        open_range = MicroarchitectureRangeList.from_string("mic_knl:")

        assert len(concrete) == len(open_range) == 1
        assert list(concrete) == list(open_range)

        assert concrete.concrete is archspec.cpu.TARGETS["mic_knl"]
        assert open_range.concrete is None
        assert concrete != open_range

    def test_concrete_round_trips_through_the_microarchitecture(self):
        """Tests that a concrete union yields back the very object from TARGETS, so that vendor,
        features and compiler information survive the round trip.
        """
        for name in ("broadwell", "neoverse_n1", "x86_64"):
            recovered = MicroarchitectureRangeList.from_string(name).concrete
            assert recovered is archspec.cpu.TARGETS[name]
            assert MicroarchitectureRangeList.from_string(str(recovered)).concrete is recovered

    def test_intersection_collapsing_to_one_microarchitecture_is_concrete(self):
        """Tests that an intersection that narrows down to a single microarchitecture reports as
        concrete, which is how a client detects that a constraint has been fully resolved.
        """
        r1 = MicroarchitectureRangeList.from_string("x86_64:skylake")
        r2 = MicroarchitectureRangeList.from_string("skylake:icelake")

        assert (r1 & r2).concrete is archspec.cpu.TARGETS["skylake"]

    def test_ambiguous_intersection_is_not_concrete(self):
        """Tests that an intersection returned as several members is not concrete, even though
        each of its members is an open range."""
        result = MicroarchitectureRangeList.from_string(
            "armv9.0a:"
        ) & MicroarchitectureRangeList.from_string("neoverse_n1:")

        assert len(result.ranges) == 2
        assert result.concrete is None


class TestRangeParsingErrors:
    """Tests that every failure while parsing a range is catchable as an ArchspecError."""

    @pytest.mark.parametrize(
        "bad_str",
        ["not_a_target", "not_a_target:", ":not_a_target", "broadwell:not_a_target"],
    )
    def test_unknown_names_raise_archspec_errors(self, bad_str):
        """Tests that an unknown microarchitecture name raises UnknownMicroarchitecture, so a
        caller can catch ArchspecError instead of a bare ValueError.
        """
        with pytest.raises(UnknownMicroarchitecture):
            MicroarchitectureRange.from_string(bad_str)
        with pytest.raises(ArchspecError):
            MicroarchitectureRangeList.from_string(bad_str)

    def test_every_parse_failure_is_an_archspec_error(self):
        """Tests that both failure modes of range parsing share the ArchspecError base, so one
        except clause covers unknown names and malformed ranges alike.
        """
        for bad_str in ("not_a_target", "broadwell:skylake:icelake", "skylake:broadwell"):
            with pytest.raises(ArchspecError):
                MicroarchitectureRangeList.from_string(bad_str)

    def test_invalid_range_is_an_archspec_error(self):
        """Tests that the exception raised for a malformed range keeps both bases, so existing
        callers that catch ValueError are unaffected.
        """
        assert issubclass(InvalidRange, ArchspecError)
        assert issubclass(InvalidRange, ValueError)


class TestRangesAreNeverEmpty:
    """Tests that a range always holds at least one microarchitecture, so that the empty set has
    a single representation, the empty union.
    """

    def test_a_range_needs_at_least_one_boundary(self):
        """Tests that constructing a range without any boundary raises, instead of yielding an
        empty range.
        """
        with pytest.raises(InvalidRange, match="a range needs at least one boundary"):
            MicroarchitectureRange()

    def test_the_empty_set_has_no_string_representation(self):
        """Tests that the display form of the empty set is not accepted as a range."""
        with pytest.raises(InvalidRange, match="has no string representation"):
            MicroarchitectureRange.from_string("{}")

    def test_every_microarchitecture_is_not_a_single_range(self):
        """Tests that the shorthand for every microarchitecture is rejected as a single range,
        since the architecture families are disjoint.
        """
        with pytest.raises(InvalidRange, match="spans several architecture families"):
            MicroarchitectureRange.from_string(":")

    def test_every_range_holds_at_least_its_lower_boundary(self):
        """Tests the invariant that makes the empty range unnecessary, over every range that can
        be built out of the known microarchitectures.
        """
        for uarch_range in every_range():
            assert uarch_range.lo in uarch_range
            assert len(uarch_range) >= 1
            assert list(uarch_range)
            # The family is always known, so no caller has to handle a None here
            assert uarch_range.family is not None


class TestTheEmptySet:
    """Tests the empty union, which is the only representation of the empty set of
    microarchitectures.
    """

    def test_an_unsatisfiable_intersection_reaches_it(self):
        """Tests that narrowing a constraint down to nothing yields the empty union, rather than
        raising.
        """
        result = MicroarchitectureRangeList.from_string(
            "broadwell:"
        ) & MicroarchitectureRangeList.from_string("aarch64:")

        assert result.empty is True
        assert result == MicroarchitectureRangeList()

    def test_it_is_not_concrete(self):
        """Tests that the empty union denotes no microarchitecture at all."""
        assert MicroarchitectureRangeList().concrete is None

    @pytest.mark.parametrize("other_str", ["broadwell:", "x86_64:,aarch64:", "mic_knl"])
    def test_it_is_contained_in_every_union(self, other_str):
        """Tests that the empty union is a subset of any union, and that no non-empty union is a
        subset of it.
        """
        empty = MicroarchitectureRangeList()
        other = MicroarchitectureRangeList.from_string(other_str)

        assert empty <= other
        assert empty < other
        assert not other <= empty
        assert empty <= empty
        assert not empty < empty

    def test_its_display_form_is_not_accepted_back(self):
        """Tests the one asymmetry in the string grammar: the empty union prints as ``{}`` so it
        stays visible in messages, but that form cannot be parsed.
        """
        empty = MicroarchitectureRangeList()

        assert str(empty) == "{}"
        with pytest.raises(InvalidRange, match="has no string representation"):
            MicroarchitectureRangeList.from_string(str(empty))


class TestMicroarchitectureRangeUnions:
    """Tests the union operator on lists of ranges, which is total since joining members never
    needs to recompute a boundary.
    """

    @pytest.mark.parametrize(
        "l1_str,l2_str,expected_str",
        [
            # Disjoint members of the same family stay side by side
            ("broadwell:skylake", "zen4:", "broadwell:skylake,zen4:"),
            # Members from different families can be joined, which is why the type exists
            ("broadwell:", "aarch64:", "aarch64:,broadwell:"),
            # A member contained in the other is absorbed by normalization
            ("broadwell:skylake", "x86_64:", "x86_64:"),
            ("skylake", "broadwell:icelake", "broadwell:icelake"),
            # Union with itself changes nothing
            ("broadwell:", "broadwell:", "broadwell:"),
            # The two sides of a bifurcation are incomparable, so both survive
            ("cascadelake:", "cannonlake:", "cannonlake:,cascadelake:"),
            # Unions with more than one member
            ("broadwell:skylake,zen4:", "aarch64:", "aarch64:,broadwell:skylake,zen4:"),
        ],
    )
    def test_union(self, l1_str, l2_str, expected_str):
        """Tests that the union of two unions gives the expected union, and that it commutes."""
        l1 = MicroarchitectureRangeList.from_string(l1_str)
        l2 = MicroarchitectureRangeList.from_string(l2_str)
        expected = MicroarchitectureRangeList.from_string(expected_str)

        assert l1 | l2 == expected
        assert l2 | l1 == expected
        assert str(l1 | l2) == expected_str

    def test_union_algebraic_laws(self):
        """Tests that the union is idempotent, commutative, and that the empty union is its
        identity element.
        """
        empty = MicroarchitectureRangeList()
        sample_lists = every_sample_list()
        for uarch_list in sample_lists:
            assert uarch_list | uarch_list == uarch_list
            assert uarch_list | empty == uarch_list
            assert empty | uarch_list == uarch_list

        for l1, l2 in itertools.combinations(sample_lists, 2):
            assert l1 | l2 == l2 | l1

    def test_union_is_associative(self):
        """Tests that the union is associative."""
        for l1, l2, l3 in itertools.combinations(every_sample_list(), 3):
            assert (l1 | l2) | l3 == l1 | (l2 | l3)

    def test_union_is_the_exact_set_union(self):
        """Tests that the union holds exactly the microarchitectures of its two operands, and
        that both of them are contained in it.
        """
        for l1, l2 in itertools.combinations(every_sample_list(), 2):
            result = l1 | l2
            assert set(result) == set(l1) | set(l2)
            assert l1 <= result
            assert l2 <= result

    def test_absorption_laws(self):
        """Tests that union and intersection absorb one another, and that intersection
        distributes over union.

        These are checked on the microarchitectures the two operations enumerate, and not on the
        boundaries: an intersection recomputes its boundaries, so it is only exact over the
        microarchitectures known today.
        """
        sample_lists = every_sample_list()
        for l1, l2 in itertools.combinations(sample_lists, 2):
            assert set(l1 & (l1 | l2)) == set(l1)
            assert set(l1 | (l1 & l2)) == set(l1)

        for l1, l2, l3 in itertools.combinations(sample_lists, 3):
            assert set(l1 & (l2 | l3)) == set((l1 & l2) | (l1 & l3))

    def test_union_rejects_invalid_types(self):
        """Tests that a union can only be joined with another union."""
        uarch_list = MicroarchitectureRangeList.from_string("broadwell:")
        with pytest.raises(TypeError, match="unsupported operand"):
            uarch_list | MicroarchitectureRange.from_string("broadwell:")


class TestEveryMicroarchitecture:
    """Tests the ``:`` shorthand, which is the union of every architecture family."""

    def test_it_covers_every_known_microarchitecture(self):
        """Tests that the shorthand holds every microarchitecture in the JSON database, which
        also shows that it is derived from it rather than hardcoded.
        """
        everything = MicroarchitectureRangeList.from_string(":")

        assert set(everything) == set(archspec.cpu.TARGETS.values())
        assert len(everything) == len(archspec.cpu.TARGETS)

    def test_it_has_one_open_member_per_family(self):
        """Tests that the shorthand expands to one range per architecture family, each unbounded
        above so that microarchitectures added in the future fall in it too.
        """
        everything = MicroarchitectureRangeList.from_string(":")
        families = {x.family for x in archspec.cpu.TARGETS.values()}

        assert len(everything.ranges) == len(families)
        assert {x.lo for x in everything.ranges} == families
        assert all(x.hi is None for x in everything.ranges)

    def test_every_union_is_contained_in_it(self):
        """Tests that the shorthand is the greatest element, so that intersecting with it changes
        nothing.
        """
        everything = MicroarchitectureRangeList.from_string(":")
        for uarch_list in every_sample_list():
            assert uarch_list <= everything
            assert set(uarch_list & everything) == set(uarch_list)

    def test_it_is_a_shorthand_and_not_a_canonical_form(self):
        """Tests that the shorthand renders back as the explicit list of families, which is what
        round-trips, so that ``:`` never appears in the output of ``str``.
        """
        everything = MicroarchitectureRangeList.from_string(":")
        explicit = str(everything)

        assert explicit != ":"
        assert MicroarchitectureRangeList.from_string(explicit) == everything
        assert explicit.startswith("aarch64:,")

    @pytest.mark.parametrize("list_str", [":", " : ", "\t:\n"])
    def test_surrounding_whitespace_is_ignored(self, list_str):
        """Tests that the shorthand is recognized regardless of surrounding whitespace."""
        assert MicroarchitectureRangeList.from_string(list_str) == (
            MicroarchitectureRangeList.from_string(":")
        )

    @pytest.mark.parametrize("list_str", [":,broadwell:", "broadwell:,:", "aarch64:,:,x86_64:"])
    def test_it_is_only_recognized_as_the_whole_string(self, list_str):
        """Tests that the shorthand is not accepted as one member of a comma separated list, so
        that every member of a parsed union is a real range.
        """
        with pytest.raises(InvalidRange, match="spans several architecture families"):
            MicroarchitectureRangeList.from_string(list_str)


class TestRangeBoundaryCoercion:
    """Tests that a range accepts its boundaries as names as well as objects, which is the same
    convenience the comparison operators on a microarchitecture already offer.
    """

    @pytest.mark.parametrize(
        "lo,hi,expected_str",
        [
            ("broadwell", "skylake", "broadwell:skylake"),
            ("broadwell", None, "broadwell:"),
            (None, "skylake", "x86_64:skylake"),
            ("broadwell", "broadwell", "broadwell"),
        ],
    )
    def test_boundaries_can_be_names(self, lo, hi, expected_str):
        """Tests that a range built from names is the same range as one built from objects."""
        from_names = MicroarchitectureRange(lo=lo, hi=hi)
        from_objects = MicroarchitectureRange(
            lo=None if lo is None else archspec.cpu.TARGETS[lo],
            hi=None if hi is None else archspec.cpu.TARGETS[hi],
        )

        assert from_names == from_objects
        assert str(from_names) == expected_str
        # The boundaries are coerced to real objects, so the whole interface works, and not just
        # the ones that get away with comparing strings
        assert from_names.family is archspec.cpu.TARGETS["x86_64"]
        assert from_names.lo in from_names
        assert from_names <= from_objects

    def test_inconsistent_names_are_still_rejected(self):
        """Tests that validation happens after coercion, so that names cannot sneak past the
        boundary check by comparing as strings.
        """
        # 'broadwell' <= 'skylake' as strings, but the microarchitectures are the other way round
        with pytest.raises(InvalidRange, match="is not compatible with"):
            MicroarchitectureRange(lo="skylake", hi="broadwell")

    @pytest.mark.parametrize("boundary", [42, 3.14, ["broadwell"]])
    def test_boundaries_of_other_types_are_rejected(self, boundary):
        """Tests that a boundary that is neither a name nor a microarchitecture raises, instead of
        building a range whose properties fail later.
        """
        with pytest.raises(TypeError, match="only objects of string or Microarchitecture"):
            MicroarchitectureRange(lo=boundary)

        with pytest.raises(TypeError, match="only objects of string or Microarchitecture"):
            MicroarchitectureRange(hi=boundary)

    def test_unknown_boundary_names_are_rejected(self):
        """Tests that an unknown boundary name raises an ArchspecError."""
        with pytest.raises(UnknownMicroarchitecture, match="unknown micro-architecture"):
            MicroarchitectureRange(lo="not_a_target")


class TestRangesWithCustomMicroarchitectures:
    """Tests ranges whose boundaries are not in the JSON database, which a client can build with
    ``generic_microarchitecture``.
    """

    def test_a_range_over_a_custom_microarchitecture_is_not_empty(self):
        """Tests that the boundaries count as members even when they are absent from TARGETS, so
        that iteration and length agree with membership.
        """
        uarch = archspec.cpu.generic_microarchitecture("my_cpu")
        uarch_range = MicroarchitectureRange(lo=uarch)

        assert uarch in uarch_range
        assert len(uarch_range) == 1
        assert list(uarch_range) == [uarch]

    def test_a_union_over_a_custom_microarchitecture_agrees_with_itself(self):
        """Tests that ``empty`` and ``len`` cannot disagree for a union built on a boundary that
        is not in the database.
        """
        uarch = archspec.cpu.generic_microarchitecture("my_cpu")
        uarch_list = MicroarchitectureRangeList([MicroarchitectureRange(lo=uarch)])

        assert uarch_list.empty is False
        assert len(uarch_list) == 1
        assert uarch in uarch_list


class TestIterationOrderIsMemoized:
    """Tests that the order iteration yields microarchitectures in is computed once, next to the
    set of known microarchitectures it sorts.
    """

    @pytest.mark.parametrize("uarch_str", ["x86_64:", "broadwell:icelake", "mic_knl"])
    def test_a_range_sorts_once(self, uarch_str):
        """Tests that iterating a range repeatedly reuses the order computed the first time."""
        uarch_range = MicroarchitectureRange.from_string(uarch_str)
        assert uarch_range._sorted is None  # pylint: disable=protected-access

        first = list(uarch_range)
        memoized = uarch_range._sorted  # pylint: disable=protected-access
        second = list(uarch_range)

        assert memoized is not None
        # The very same tuple backs the second iteration, so nothing was sorted again
        assert uarch_range._sorted is memoized  # pylint: disable=protected-access
        assert first == second == list(memoized)

    @pytest.mark.parametrize("list_str", ["x86_64:,aarch64:", "broadwell:icelake", ":"])
    def test_a_union_sorts_once(self, list_str):
        """Tests the same for a union of ranges."""
        uarch_list = MicroarchitectureRangeList.from_string(list_str)
        assert uarch_list._sorted is None  # pylint: disable=protected-access

        first = list(uarch_list)
        memoized = uarch_list._sorted  # pylint: disable=protected-access
        second = list(uarch_list)

        assert memoized is not None
        assert uarch_list._sorted is memoized  # pylint: disable=protected-access
        assert first == second == list(memoized)

    def test_the_order_is_still_topological(self):
        """Tests that memoizing does not disturb the order, which must keep ancestors before
        their descendants for both types.
        """
        for uarch_set in (
            MicroarchitectureRange.from_string("x86_64:"),
            MicroarchitectureRangeList.from_string("x86_64:,aarch64:"),
        ):
            result = list(uarch_set)
            for index, uarch in enumerate(result):
                assert not [x for x in result[:index] if uarch < x], f"{uarch} is out of order"
