# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""Ranges of CPU microarchitectures, and unions of them.

Microarchitectures form a partial order, but not a lattice, so a range is closed under neither
union nor intersection. Both operations therefore live on ``MicroarchitectureRangeList``, where
they are total.
"""
from typing import FrozenSet, Iterable, Iterator, List, Optional, Tuple, Union

from .microarchitecture import TARGETS, InvalidRange, InvalidType, Microarchitecture


def _topological_order(
    targets: Iterable[Microarchitecture],
) -> Tuple[Microarchitecture, ...]:
    """Returns the microarchitectures passed as input in a deterministic topological order, with
    the most generic ones first.
    """
    # Sorting by the number of ancestors is a topological order, since an ancestor always has
    # strictly fewer ancestors than its descendants.
    return tuple(sorted(targets, key=lambda x: (len(x.ancestors), x.name)))


def _as_microarchitecture(item: Union[str, Microarchitecture]) -> Microarchitecture:
    """Returns the microarchitecture for the item passed as input, which can be either a name or
    a ``Microarchitecture`` already.

    Raises:
        InvalidType: if the item is neither a string nor a Microarchitecture
        UnknownMicroarchitecture: if the name is not a known microarchitecture
    """
    if isinstance(item, str):
        return Microarchitecture.from_string(item)

    if not isinstance(item, Microarchitecture):
        msg = "only objects of string or Microarchitecture types are accepted [got {0}]"
        raise InvalidType(msg.format(str(type(item))))

    return item


#: Error message for the empty set, which is deliberately not part of the string grammar. It is a
#: state a client can reach through the API, but not one it can spell.
_EMPTY_SET_IS_NOT_A_RANGE = (
    "the empty set of microarchitectures has no string representation, and can only be built as "
    "an empty MicroarchitectureRangeList"
)

#: Error message for ':', which is a valid list, but never a valid single range
_EVERY_MICROARCHITECTURE_IS_NOT_A_RANGE = (
    "':' is not a microarchitecture range, since every microarchitecture spans several "
    "architecture families; use a MicroarchitectureRangeList instead"
)


class MicroarchitectureRange:
    """A range of micro-architectures"""

    def __init__(
        self,
        *,
        lo: Optional[Union[str, Microarchitecture]] = None,
        hi: Optional[Union[str, Microarchitecture]] = None,
    ) -> None:
        """Represents a range of microarchitectures, defined by a lower and an upper boundary.

        Either boundary can be given as a name or as a ``Microarchitecture``, and either can be
        omitted, but not both. They must maintain logical consistency when defined.

        If the upper boundary is None, the range is unbounded above. The lower boundary can
        always be inferred from the upper boundary, and corresponds to its family.

        A range always holds at least its own lower boundary, so it is never empty. The empty set
        of microarchitectures is an empty ``MicroarchitectureRangeList``, which keeps a single
        representation for it.

        Ranges are compared by their boundaries, and not by the microarchitectures they currently
        enumerate. This keeps comparisons stable when new microarchitectures are added to the JSON
        data: ``mic_knl:`` and ``mic_knl:mic_knl`` are different ranges, even though today
        ``mic_knl`` has no descendant and both enumerate the same single microarchitecture.

        A range is closed under neither union nor intersection, since microarchitectures form a
        partial order that is not a lattice: two ranges can overlap, or sit side by side, without
        the result having a unique boundary. Both operations therefore live on
        ``MicroarchitectureRangeList``, where they are total.

        Args:
            lo: The lower boundary of the microarchitecture range, as a name or an object.
            hi: The upper boundary of the microarchitecture range, as a name or an object.

        Raises:
            InvalidRange: If the provided range boundaries are not consistent, or if both
                boundaries are None
            InvalidType: If a boundary is neither a string nor a Microarchitecture
            UnknownMicroarchitecture: If a boundary name is not a known microarchitecture
        """
        lower = None if lo is None else _as_microarchitecture(lo)
        upper = None if hi is None else _as_microarchitecture(hi)

        if lower is None:
            if upper is None:
                raise InvalidRange(
                    "a range needs at least one boundary; the empty set of microarchitectures "
                    "is an empty MicroarchitectureRangeList"
                )
            # lo can be inferred from hi, but not vice versa
            lower = upper.family
        elif upper is not None and not lower <= upper:
            raise InvalidRange(
                f"the range ({lower}, {upper}) is invalid, since '{lower}' is not compatible "
                f"with '{upper}'"
            )

        self.lo = lower
        self.hi = upper

        # The known microarchitectures in this range, computed lazily since it is only needed
        # for iteration and for intersections, and the order iteration yields them in
        self._targets: Optional[FrozenSet[Microarchitecture]] = None
        self._sorted: Optional[Tuple[Microarchitecture, ...]] = None

    @property
    def family(self) -> Microarchitecture:
        """The architecture family this range belongs to"""
        return self.lo.family

    @property
    def concrete(self) -> Optional[Microarchitecture]:
        """The single microarchitecture this range denotes, or None if it denotes more than one.

        A range is concrete when both boundaries are the same microarchitecture, which is what
        ``from_string`` builds for a bare name. Note that this is a property of the boundaries,
        not of the microarchitectures known today: ``mic_knl:`` is not concrete even though
        ``mic_knl`` currently has no descendant, because a future descendant would fall in it.
        """
        if self.lo != self.hi:
            return None
        return self.lo

    @property
    def _known_targets(self) -> FrozenSet[Microarchitecture]:
        """The known microarchitectures that fall in this range."""
        if self._targets is None:
            known = {x for x in TARGETS.values() if x in self}
            # The boundaries belong to the range by construction, so they are added even when
            # they are not in TARGETS. That keeps a range from ever enumerating as empty.
            known.add(self.lo)
            if self.hi is not None:
                known.add(self.hi)
            self._targets = frozenset(known)
        return self._targets

    def __contains__(self, item: Union[str, Microarchitecture]) -> bool:
        uarch = _as_microarchitecture(item)
        return self.lo <= uarch and (self.hi is None or uarch <= self.hi)

    def __iter__(self) -> Iterator[Microarchitecture]:
        # Memoized alongside the set itself, so that repeated iteration does not re-sort
        if self._sorted is None:
            self._sorted = _topological_order(self._known_targets)
        return iter(self._sorted)

    def __len__(self) -> int:
        return len(self._known_targets)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MicroarchitectureRange):
            return NotImplemented
        return self.lo == other.lo and self.hi == other.hi

    def __hash__(self) -> int:
        return hash((self.lo, self.hi))

    def __le__(self, other: object) -> bool:
        """True if every microarchitecture in this range is also in other."""
        if not isinstance(other, MicroarchitectureRange):
            return NotImplemented

        if self.family != other.family:
            return False

        if not other.lo <= self.lo:
            return False

        if other.hi is None:
            return True

        return self.hi is not None and self.hi <= other.hi

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, MicroarchitectureRange):
            return NotImplemented
        return self <= other and self != other

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, MicroarchitectureRange):
            return NotImplemented
        return other <= self

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, MicroarchitectureRange):
            return NotImplemented
        return other < self

    @staticmethod
    def from_string(range_str: str) -> "MicroarchitectureRange":
        """Returns a microarchitecture range from its string representation.

        The accepted formats are ``lo:hi``, ``lo:`` and ``:hi`` for bounded and unbounded
        ranges, and a bare ``name`` for a range holding a single microarchitecture.

        Neither the empty set nor the set of every microarchitecture is a range, so ``{}`` and
        ``:`` are rejected here. Both are expressible as a ``MicroarchitectureRangeList``.

        Raises:
            InvalidRange: if the string is not a valid range
            ValueError: if a boundary is not a valid microarchitecture name
        """
        range_str = range_str.strip()
        if range_str == "{}":
            raise InvalidRange(_EMPTY_SET_IS_NOT_A_RANGE)

        if range_str == ":":
            raise InvalidRange(_EVERY_MICROARCHITECTURE_IS_NOT_A_RANGE)

        if ":" not in range_str:
            uarch = Microarchitecture.from_string(range_str)
            return MicroarchitectureRange(lo=uarch, hi=uarch)

        parts = range_str.split(":")
        if len(parts) != 2:
            raise InvalidRange(f"'{range_str}' is not a valid microarchitecture range")

        lo_str, hi_str = (x.strip() for x in parts)
        return MicroarchitectureRange(
            lo=Microarchitecture.from_string(lo_str) if lo_str else None,
            hi=Microarchitecture.from_string(hi_str) if hi_str else None,
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(lo={self.lo!r}, hi={self.hi!r})"

    def __str__(self) -> str:
        if self.hi is None:
            return f"{self.lo}:"

        # A range holding a single microarchitecture is rendered as a bare name, which is how
        # "from_string" parses it back. No other range renders that way, so the string
        # representation stays a faithful encoding of the boundaries.
        if self.lo == self.hi:
            return str(self.lo)

        return f"{self.lo}:{self.hi}"


def _family_roots() -> List[Microarchitecture]:
    """Returns the root of every architecture family known to the JSON database."""
    # Recomputed on each call, since TARGETS can be swapped e.g. by setting
    # ARCHSPEC_EXTENSION_CPU_DIR, and a union built from it is meant to reflect the database as
    # it is when the union is built
    return [x for x in TARGETS.values() if not x.ancestors]


def _minimal(targets: Iterable[Microarchitecture]) -> List[Microarchitecture]:
    """Returns the minimal elements of a set of microarchitectures, i.e. those that have no
    other element of the set below them.
    """
    targets = list(targets)
    return [x for x in targets if not any(y < x for y in targets)]


def _maximal(targets: Iterable[Microarchitecture]) -> List[Microarchitecture]:
    """Returns the maximal elements of a set of microarchitectures, i.e. those that have no
    other element of the set above them.
    """
    targets = list(targets)
    return [x for x in targets if not any(y > x for y in targets)]


def _intersect_ranges(
    r1: MicroarchitectureRange, r2: MicroarchitectureRange
) -> List[MicroarchitectureRange]:
    """Returns the intersection of two ranges, as a list of ranges whose union holds exactly the
    known microarchitectures that belong to both of them.

    This is a total operation: a set with several minimal or maximal elements has no unique
    boundary, and so is not expressible as a single range, but it is always expressible as a
    union of them. When the intersection does have unique boundaries, the returned list holds
    exactly the one range between them.

    The result is exact over the *known* microarchitectures. A microarchitecture added to the
    JSON database in the future may fall inside the intersection without being covered by any
    of the returned ranges, which is the same caveat that iteration over a range already has.
    """
    if r1.family != r2.family:
        return []

    # Reading the memoized set of known targets is what makes this exact

    common = r1._known_targets & r2._known_targets  # pylint: disable=protected-access
    if not common:
        return []

    upper_boundaries: List[Optional[Microarchitecture]]
    if r1.hi is None and r2.hi is None:
        # Both ranges are unbounded above, so the intersection is unbounded above too, and must
        # stay open to keep matching microarchitectures added in the future.
        upper_boundaries = [None]
    else:
        # If exactly one range is bounded above, its upper boundary belongs to the common set
        # and is its maximum, so taking the maximal elements covers that case too.
        upper_boundaries = list(_maximal(common))

    return [
        MicroarchitectureRange(lo=lo, hi=hi)
        for lo in _minimal(common)
        for hi in upper_boundaries
        if hi is None or lo <= hi
    ]


class MicroarchitectureRangeList:
    """An ordered, deduplicated union of microarchitecture ranges."""

    def __init__(self, ranges: Iterable[MicroarchitectureRange] = ()) -> None:
        """Represents the union of a list of microarchitecture ranges.

        The members are normalized on construction: duplicates and ranges that are contained in
        another member are dropped, and what is left is sorted so that the string representation
        is stable.

        A union with no members is the empty set of microarchitectures. Since a range is never
        empty, this is the only representation for it.

        Unlike a single range, a union is closed under both union and intersection, so ``|`` and
        ``&`` are total operations that never raise.

        Args:
            ranges: the ranges to be joined in a union

        Raises:
            InvalidType: If a member is not a MicroarchitectureRange
        """
        unique: List[MicroarchitectureRange] = []
        for current in ranges:
            # A range is itself iterable, so a caller passing a single one instead of a list of
            # them would otherwise build a union of microarchitectures, and only fail much later
            if not isinstance(current, MicroarchitectureRange):
                msg = "only objects of MicroarchitectureRange type are accepted [got {0}]"
                raise InvalidType(msg.format(str(type(current))))

            if current in unique:
                continue
            unique.append(current)

        self.ranges: Tuple[MicroarchitectureRange, ...] = tuple(
            sorted((x for x in unique if not any(x < y for y in unique)), key=str)
        )

        # The known microarchitectures in this union, computed lazily, and the order iteration
        # yields them in
        self._targets: Optional[FrozenSet[Microarchitecture]] = None
        self._sorted: Optional[Tuple[Microarchitecture, ...]] = None

    @property
    def empty(self) -> bool:
        """True if the union contains no microarchitecture, False otherwise"""
        return not self.ranges

    @property
    def concrete(self) -> Optional[Microarchitecture]:
        """The single microarchitecture this union denotes, or None if it denotes more than one.

        A union is concrete when it has exactly one member and that member is a concrete range.
        Use this rather than ``len(self) == 1`` to recover a single microarchitecture: see the
        note in ``__len__`` for why the two are not the same question.
        """
        if len(self.ranges) != 1:
            return None
        return self.ranges[0].concrete

    @property
    def _known_targets(self) -> FrozenSet[Microarchitecture]:
        """The known microarchitectures that fall in this union."""
        if self._targets is None:
            # pylint: disable=protected-access
            self._targets = frozenset().union(*(x._known_targets for x in self.ranges))
        return self._targets

    def __contains__(self, item: Union[str, Microarchitecture]) -> bool:
        uarch = _as_microarchitecture(item)
        return any(uarch in x for x in self.ranges)

    def __iter__(self) -> Iterator[Microarchitecture]:
        # Memoized alongside the set itself, so that repeated iteration does not re-sort
        if self._sorted is None:
            self._sorted = _topological_order(self._known_targets)
        return iter(self._sorted)

    def __len__(self) -> int:
        """The number of known microarchitectures in the union, not the number of members.

        This keeps ``len`` consistent with iteration and membership, as it is for a single
        range. Use the ``ranges`` attribute to inspect the members.

        Beware that ``len(self) == 1`` does *not* mean the union denotes a single
        microarchitecture: it is also true of ``mic_knl:``, an open range that happens to have
        one member in the database today and would gain more if a descendant were added. Use the
        ``concrete`` property for that question, since it looks at the boundaries instead.
        """
        return len(self._known_targets)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MicroarchitectureRangeList):
            return NotImplemented
        return self.ranges == other.ranges

    def __hash__(self) -> int:
        return hash(self.ranges)

    def __le__(self, other: object) -> bool:
        """True if every member of this union is contained in a member of other.

        This is a conservative check: it is sufficient for containment, but not necessary, since
        a member could be covered by several members of other without sitting inside any single
        one of them. Being member-wise, it agrees with ``MicroarchitectureRange.__le__``, which
        compares boundaries rather than the microarchitectures that are known today.
        """
        if not isinstance(other, MicroarchitectureRangeList):
            return NotImplemented
        return all(any(x <= y for y in other.ranges) for x in self.ranges)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, MicroarchitectureRangeList):
            return NotImplemented
        return self <= other and self != other

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, MicroarchitectureRangeList):
            return NotImplemented
        return other <= self

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, MicroarchitectureRangeList):
            return NotImplemented
        return other < self

    def __or__(self, other: "MicroarchitectureRangeList") -> "MicroarchitectureRangeList":
        """Returns the union of two unions of ranges.

        This operation is total, and never raises: the members of both operands are joined, and
        the constructor normalizes them. Unlike the intersection, it is exact for
        microarchitectures added to the JSON database in the future too, since it never needs to
        recompute a boundary.
        """
        if not isinstance(other, MicroarchitectureRangeList):
            return NotImplemented

        return MicroarchitectureRangeList(self.ranges + other.ranges)

    def __and__(self, other: "MicroarchitectureRangeList") -> "MicroarchitectureRangeList":
        """Returns the intersection of two unions of ranges.

        This operation is total, and never raises: an intersection that has no unique boundary
        is returned as a union of more than one range.
        """
        if not isinstance(other, MicroarchitectureRangeList):
            return NotImplemented

        result: List[MicroarchitectureRange] = []
        for r1 in self.ranges:
            for r2 in other.ranges:
                result.extend(_intersect_ranges(r1, r2))
        return MicroarchitectureRangeList(result)

    @staticmethod
    def from_string(list_str: str) -> "MicroarchitectureRangeList":
        """Returns a union of microarchitecture ranges from its string representation, which is
        a comma separated list of ranges.

        A bare ``:`` is accepted as a shorthand for every microarchitecture, and expands to one
        open range per architecture family. It is only recognized as the whole string, and is a
        shorthand rather than a canonical form: the union it returns renders as the explicit list
        of families, and covers the families known to the JSON database at the time of the call.

        The empty set has no string representation, so both ``{}`` and the empty string are
        rejected. Build it as ``MicroarchitectureRangeList()``.

        Raises:
            InvalidRange: if the list is malformed, or if one of its members is not a valid range
            ValueError: if a boundary is not a valid microarchitecture name
        """
        list_str = list_str.strip()
        if list_str == ":":
            return MicroarchitectureRangeList(
                MicroarchitectureRange(lo=x) for x in _family_roots()
            )

        if not list_str:
            raise InvalidRange(_EMPTY_SET_IS_NOT_A_RANGE)

        members = [x.strip() for x in list_str.split(",")]
        # Caught here rather than in the member parser, which would report an unknown
        # microarchitecture named '' and point away from the malformed list
        if not all(members):
            raise InvalidRange(
                f"'{list_str}' is not a valid list of microarchitecture ranges, since one of "
                f"its members is empty"
            )

        return MicroarchitectureRangeList(MicroarchitectureRange.from_string(x) for x in members)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({list(self.ranges)!r})"

    def __str__(self) -> str:
        if not self.ranges:
            # A display marker, so that an unsatisfiable result stays visible when interpolated
            # in a message. It is deliberately not accepted back by "from_string", which makes
            # the empty set the only union that does not round-trip.
            return "{}"
        return ",".join(str(x) for x in self.ranges)
