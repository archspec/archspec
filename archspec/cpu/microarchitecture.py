# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""Types and functions to manage information on CPU microarchitectures."""
import functools
import platform
import re
import sys
import warnings
from typing import (
    IO,
    Any,
    Dict,
    FrozenSet,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from . import schema
from .alias import FEATURE_ALIASES
from .schema import LazyDictionary


def coerce_target_names(func):
    """Decorator that automatically converts a known target name to a proper
    Microarchitecture object.
    """

    @functools.wraps(func)
    def _impl(self, other):
        if isinstance(other, str):
            if other not in TARGETS:
                msg = '"{0}" is not a valid target name'
                raise UnknownMicroarchitecture(msg.format(other))
            other = TARGETS[other]

        return func(self, other)

    return _impl


class Microarchitecture:
    """A specific CPU micro-architecture"""

    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-instance-attributes
    #: Aliases for micro-architecture's features
    feature_aliases = FEATURE_ALIASES

    def __init__(
        self,
        name: str,
        parents: List["Microarchitecture"],
        vendor: str,
        features: Set[str],
        compilers: Dict[str, List[Dict[str, str]]],
        generation: int = 0,
        cpu_part: str = "",
    ):
        """
        Args:
            name: name of the micro-architecture (e.g. ``icelake``)
            parents: list of parent micro-architectures, if any. Parenthood is considered by
                cpu features and not chronologically. As such, each micro-architecture is
                compatible with its ancestors. For example, ``skylake``, which has ``broadwell``
                as a parent, supports running binaries optimized for ``broadwell``.
            vendor: vendor of the micro-architecture
            features: supported CPU flags. Note that the semantic of the flags in this field might
                vary among architectures, if at all present. For instance, x86_64 processors will
                list all the flags supported by a given CPU, while Arm processors will list instead
                only the flags that have been added on top of the base model for the current
                micro-architecture.
            compilers: compiler support to generate tuned code for this micro-architecture. This
                dictionary has as keys names of supported compilers, while values are a list of
                dictionaries with fields:

                * name: name of the micro-architecture according to the compiler. This is the name
                    passed to the ``-march`` option or similar. Not needed if it is the same as
                    ``self.name``.
                * versions: versions that support this micro-architecture.
                * flags: flags to be passed to the compiler to generate optimized code

            generation: generation of the micro-architecture, if relevant.
            cpu_part: cpu part of the architecture, if relevant.
        """
        self.name = name
        self.parents = parents
        self.vendor = vendor
        self.features = features
        self.compilers = compilers
        # Only relevant for PowerPC
        self.generation = generation
        # Only relevant for AArch64
        self.cpu_part = cpu_part

        # Cache the "ancestor" computation
        self._ancestors: Optional[List["Microarchitecture"]] = None
        # Cache the "generic" computation
        self._generic: Optional["Microarchitecture"] = None
        # Cache the "family" computation
        self._family: Optional["Microarchitecture"] = None

        # ssse3 implies sse3; on Linux sse3 is not mentioned in /proc/cpuinfo, so add it ad-hoc.
        if "ssse3" in self.features:
            self.features.add("sse3")

    @property
    def ancestors(self) -> List["Microarchitecture"]:
        """All the ancestors of this microarchitecture."""
        if self._ancestors is None:
            value = self.parents[:]
            for parent in self.parents:
                value.extend(a for a in parent.ancestors if a not in value)
            self._ancestors = value
        return self._ancestors

    def _to_set(self) -> Set[str]:
        """Returns a set of the nodes in this microarchitecture DAG."""
        # This function is used to implement subset semantics with
        # comparison operators
        return set([str(self)] + [str(x) for x in self.ancestors])

    @coerce_target_names
    def __eq__(self, other: Union[str, "Microarchitecture"]) -> bool:
        if not isinstance(other, Microarchitecture):
            return NotImplemented

        return (
            self.name == other.name
            and self.vendor == other.vendor
            and self.features == other.features
            and self.parents == other.parents  # avoid ancestors here
            and self.compilers == other.compilers
            and self.generation == other.generation
            and self.cpu_part == other.cpu_part
        )

    def __hash__(self) -> int:
        return hash(self.name)

    @coerce_target_names
    def __ne__(self, other: Union[str, "Microarchitecture"]) -> bool:
        return not self == other

    @coerce_target_names
    def __lt__(self, other: Union[str, "Microarchitecture"]) -> bool:
        if not isinstance(other, Microarchitecture):
            return NotImplemented

        return self._to_set() < other._to_set()

    @coerce_target_names
    def __le__(self, other: Union[str, "Microarchitecture"]) -> bool:
        return (self == other) or (self < other)

    @coerce_target_names
    def __gt__(self, other: Union[str, "Microarchitecture"]) -> bool:
        if not isinstance(other, Microarchitecture):
            return NotImplemented

        return self._to_set() > other._to_set()

    @coerce_target_names
    def __ge__(self, other: Union[str, "Microarchitecture"]) -> bool:
        return (self == other) or (self > other)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r})"

    def __str__(self) -> str:
        return self.name

    def tree(self, fp: IO[str] = sys.stdout, indent: int = 2) -> None:
        """Format the partial order of this microarchitecture's ancestors as a tree."""
        seen: Set[str] = set()
        stack: List[Tuple[int, Microarchitecture]] = [(0, self)]
        while stack:
            level, current = stack.pop()
            print(f"{'':>{level}}{current.name}", file=fp)

            for parent in reversed(current.parents):
                if parent.name in seen:
                    continue
                stack.append((level + indent, parent))
                seen.add(parent.name)

    def __contains__(self, feature: str) -> bool:
        # Feature must be of a string type, so be defensive about that
        if not isinstance(feature, str):
            msg = "only objects of string types are accepted [got {0}]"
            raise TypeError(msg.format(str(type(feature))))

        # Here we look first in the raw features, and fall-back to
        # feature aliases if not match was found
        if feature in self.features:
            return True

        # Check if the alias is defined, if not it will return False
        match_alias = Microarchitecture.feature_aliases.get(feature, lambda x: False)
        return match_alias(self)

    @property
    def family(self) -> "Microarchitecture":
        """Returns the architecture family a given target belongs to"""
        if self._family is None:
            roots = [x for x in [self] + self.ancestors if not x.ancestors]
            msg = "a target is expected to belong to just one architecture family"
            msg += f"[found {', '.join(str(x) for x in roots)}]"
            assert len(roots) == 1, msg
            self._family = roots.pop()

        return self._family

    @property
    def generic(self) -> "Microarchitecture":
        """Returns the best generic architecture that is compatible with self"""
        if self._generic is None:
            generics = [x for x in [self] + self.ancestors if x.vendor == "generic"]
            self._generic = max(generics, key=lambda x: len(x.ancestors))
        return self._generic

    def to_dict(self) -> Dict[str, Any]:
        """Returns a dictionary representation of this object."""
        return {
            "name": str(self.name),
            "vendor": str(self.vendor),
            "features": sorted(str(x) for x in self.features),
            "generation": self.generation,
            "parents": [str(x) for x in self.parents],
            "compilers": self.compilers,
            "cpupart": self.cpu_part,
        }

    @staticmethod
    def from_dict(data) -> "Microarchitecture":
        """Construct a microarchitecture from a dictionary representation."""
        return Microarchitecture(
            name=data["name"],
            parents=[TARGETS[x] for x in data["parents"]],
            vendor=data["vendor"],
            features=set(data["features"]),
            compilers=data.get("compilers", {}),
            generation=data.get("generation", 0),
            cpu_part=data.get("cpupart", ""),
        )

    @staticmethod
    def from_string(name: str) -> "Microarchitecture":
        """Returns a micro-architecture from its name.

        Raises:
            UnknownMicroarchitecture: if the name is not a valid microarchitecture
        """
        if name not in TARGETS:
            raise UnknownMicroarchitecture(f"unknown micro-architecture '{name}'")
        return TARGETS[name]

    def optimization_flags(self, compiler: str, version: str) -> str:
        """Returns a string containing the optimization flags that needs to be used to produce
        code optimized for this micro-architecture.

        The version is expected to be a string of dot-separated digits.

        If there is no information on the compiler passed as an argument, the function returns an
        empty string. If it is known that the compiler version we want to use does not support
        this architecture, the function raises an exception.

        Args:
            compiler: name of the compiler to be used
            version: version of the compiler to be used

        Raises:
            UnsupportedMicroarchitecture: if the requested compiler does not support
                this micro-architecture.
            ValueError: if the version doesn't match the expected format
        """
        # If we don't have information on compiler at all return an empty string
        if compiler not in self.family.compilers:
            return ""

        # If we have information, but it stops before this
        # microarchitecture, fall back to the best known target
        if compiler not in self.compilers:
            best_target = [x for x in self.ancestors if compiler in x.compilers][0]
            msg = (
                "'{0}' compiler is known to optimize up to the '{1}'"
                " microarchitecture in the '{2}' architecture family"
            )
            msg = msg.format(compiler, best_target, best_target.family)
            raise UnsupportedMicroarchitecture(msg)

        # Check that the version matches the expected format
        if not re.match(r"^(?:\d+\.)*\d+$", version):
            msg = (
                "invalid format for the compiler version argument. "
                "Only dot separated digits are allowed."
            )
            raise InvalidCompilerVersion(msg)

        # If we have information on this compiler we need to check the
        # version being used
        compiler_info = self.compilers[compiler]

        def satisfies_constraint(entry, version):
            min_version, max_version = entry["versions"].split(":")

            # Check version suffixes
            min_version, _ = version_components(min_version)
            max_version, _ = version_components(max_version)
            version, _ = version_components(version)

            # Assume compiler versions fit into semver
            def tuplify(ver):
                return tuple(int(y) for y in ver.split("."))

            version = tuplify(version)
            if min_version:
                min_version = tuplify(min_version)
                if min_version > version:
                    return False

            if max_version:
                max_version = tuplify(max_version)
                if max_version < version:
                    return False

            return True

        for compiler_entry in compiler_info:
            if satisfies_constraint(compiler_entry, version):
                flags_fmt = compiler_entry["flags"]
                # If there's no field name, use the name of the
                # micro-architecture
                compiler_entry.setdefault("name", self.name)

                # Check if we need to emit a warning
                warning_message = compiler_entry.get("warnings", None)
                if warning_message:
                    warnings.warn(warning_message)

                flags = flags_fmt.format(**compiler_entry)
                return flags

        msg = "cannot produce optimized binary for micro-architecture '{0}' with {1}@{2}"
        if compiler_info:
            versions = [x["versions"] for x in compiler_info]
            msg += f' [supported compiler versions are {", ".join(versions)}]'
        else:
            msg += " [no supported compiler versions]"
        msg = msg.format(self.name, compiler, version)
        raise UnsupportedMicroarchitecture(msg)


class MicroarchitectureRange:
    """A range of micro-architectures"""

    def __init__(
        self, *, lo: Optional[Microarchitecture] = None, hi: Optional[Microarchitecture] = None
    ) -> None:
        """Represents a range of microarchitectures, defined by a lower and an upper boundary.

        Both boundaries are optional but must maintain logical consistency when defined.

        If a boundary is None, the range is unbounded in that direction.
        The lower boundary can always be inferred from the upper boundary and corresponds to
        the family of the upper boundary.

        If both boundaries are None, the range is empty.

        Ranges are compared by their boundaries, and not by the microarchitectures they currently
        enumerate. This keeps comparisons stable when new microarchitectures are added to the JSON
        data: ``mic_knl:`` and ``mic_knl:mic_knl`` are different ranges, even though today
        ``mic_knl`` has no descendant and both enumerate the same single microarchitecture.

        A range is closed under neither union nor intersection, since microarchitectures form a
        partial order that is not a lattice: two ranges can overlap, or sit side by side, without
        the result having a unique boundary. Both operations therefore live on
        ``MicroarchitectureRangeList``, where they are total.

        Args:
            lo: The lower boundary of the microarchitecture range.
            hi: The upper boundary of the microarchitecture range.

        Raises:
            InvalidRange: If the provided range boundaries are not consistent
        """
        if lo is not None and hi is not None and not lo <= hi:
            raise InvalidRange(
                f"the range ({lo}, {hi}) is invalid, since '{lo}' is not compatible with '{hi}'"
            )

        # lo can be inferred from hi, but not vice versa
        if lo is None and hi is not None:
            lo = hi.family

        self.lo = lo
        self.hi = hi

        # The known microarchitectures in this range, computed lazily since it is only needed
        # for iteration and for intersections
        self._targets: Optional[FrozenSet[Microarchitecture]] = None

    @property
    def empty(self) -> bool:
        """True if the range contains no microarchitecture, False otherwise"""
        # If lo could not be inferred, this is the empty set
        return self.lo is None

    @property
    def family(self) -> Optional[Microarchitecture]:
        """The architecture family this range belongs to, or None if the range is empty"""
        if self.lo is None:
            return None
        return self.lo.family

    @property
    def concrete(self) -> Optional[Microarchitecture]:
        """The single microarchitecture this range denotes, or None if it denotes more than one.

        A range is concrete when both boundaries are the same microarchitecture, which is what
        ``from_string`` builds for a bare name. Note that this is a property of the boundaries,
        not of the microarchitectures known today: ``mic_knl:`` is not concrete even though
        ``mic_knl`` currently has no descendant, because a future descendant would fall in it.
        """
        if self.lo is None or self.lo != self.hi:
            return None
        return self.lo

    @property
    def _known_targets(self) -> FrozenSet[Microarchitecture]:
        """The known microarchitectures that fall in this range."""
        if self._targets is None:
            self._targets = frozenset(x for x in TARGETS.values() if x in self)
        return self._targets

    def __contains__(self, item: Union[str, Microarchitecture]) -> bool:
        if isinstance(item, str):
            item = Microarchitecture.from_string(item)

        if not isinstance(item, Microarchitecture):
            msg = "only objects of string or Microarchitecture types are accepted [got {0}]"
            raise TypeError(msg.format(str(type(item))))

        if self.lo is None:
            return False

        return self.lo <= item and (self.hi is None or item <= self.hi)

    def __iter__(self) -> Iterator[Microarchitecture]:
        # Sorting by the number of ancestors is a topological order, since an ancestor always
        # has strictly fewer ancestors than its descendants. This yields a deterministic order,
        # with the most generic microarchitectures first.
        return iter(sorted(self._known_targets, key=lambda x: (len(x.ancestors), x.name)))

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

        # The empty range is a subset of any range, including itself
        if self.lo is None:
            return True

        if other.lo is None or self.family != other.family:
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
        ranges, a bare ``name`` for a range holding a single microarchitecture, and ``{}`` or
        ``:`` for the empty range.

        Raises:
            InvalidRange: if the string is not a valid range
            ValueError: if a boundary is not a valid microarchitecture name
        """
        range_str = range_str.strip()
        if range_str in ("{}", ":"):
            return MicroarchitectureRange()

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
        if self.lo is None:
            return "{}"

        if self.hi is None:
            return f"{self.lo}:"

        # A range holding a single microarchitecture is rendered as a bare name, which is how
        # "from_string" parses it back. No other range renders that way, so the string
        # representation stays a faithful encoding of the boundaries.
        if self.lo == self.hi:
            return str(self.lo)

        return f"{self.lo}:{self.hi}"


def microarchitecture_range(
    *, lo: Optional[str] = None, hi: Optional[str] = None
) -> MicroarchitectureRange:
    """Returns a microarchitecture range from its boundaries.

    Raises:
        ValueError: if the name is not a valid microarchitecture
    """
    lo_uarch = lo if lo is None else Microarchitecture.from_string(lo)
    hi_uarch = hi if hi is None else Microarchitecture.from_string(hi)
    return MicroarchitectureRange(lo=lo_uarch, hi=hi_uarch)


def _minimal(targets: Iterable[Microarchitecture]) -> List[Microarchitecture]:
    """Returns the minimal elements of a set of microarchitectures, i.e. those that have no
    other element of the set below them.

    For known microarchitectures ``y < x`` holds exactly when ``y`` is an ancestor of ``x``, so
    the check can be done on ancestor names. That avoids the quadratic number of set rebuilds
    that ``Microarchitecture._to_set`` would incur when comparing every pair.
    """
    targets = list(targets)
    names = {x.name for x in targets}
    return [x for x in targets if not names.intersection(a.name for a in x.ancestors)]


def _maximal(targets: Iterable[Microarchitecture]) -> List[Microarchitecture]:
    """Returns the maximal elements of a set of microarchitectures, i.e. those that have no
    other element of the set above them.

    See ``_minimal`` for why ancestor names are used instead of the comparison operators.
    """
    targets = list(targets)
    ancestor_names = {a.name for x in targets for a in x.ancestors}
    return [x for x in targets if x.name not in ancestor_names]


def _cover(r1: MicroarchitectureRange, r2: MicroarchitectureRange) -> List[MicroarchitectureRange]:
    """Returns a list of ranges whose union holds exactly the known microarchitectures that
    belong to both the ranges passed as input.

    This is a total operation: a set with several minimal or maximal elements has no unique
    boundary, and so is not expressible as a single range, but it is always expressible as a
    union of them. When the intersection does have unique boundaries, the returned list holds
    exactly the one range between them.

    The result is exact over the *known* microarchitectures. A microarchitecture added to the
    JSON database in the future may fall inside the intersection without being covered by any
    of the returned ranges, which is the same caveat that iteration over a range already has.
    """
    if r1.empty or r2.empty or r1.family != r2.family:
        return []

    # Reading the memoized set of known targets is what makes this exact

    common = r1._known_targets & r2._known_targets  # pylint: disable=protected-access
    if not common:
        return []

    his: List[Optional[Microarchitecture]]
    if r1.hi is None and r2.hi is None:
        # Both ranges are unbounded above, so the intersection is unbounded above too, and must
        # stay open to keep matching microarchitectures added in the future.
        his = [None]
    else:
        # If exactly one range is bounded above, its upper boundary belongs to the common set
        # and is its maximum, so taking the maximal elements covers that case too.
        his = list(_maximal(common))

    return [
        MicroarchitectureRange(lo=lo, hi=hi)
        for lo in _minimal(common)
        for hi in his
        if hi is None or lo <= hi
    ]


class MicroarchitectureRangeList:
    """An ordered, deduplicated union of microarchitecture ranges."""

    def __init__(self, ranges: Iterable[MicroarchitectureRange] = ()) -> None:
        """Represents the union of a list of microarchitecture ranges.

        The members are normalized on construction: empty ranges, duplicates and ranges that are
        contained in another member are dropped, and what is left is sorted so that the string
        representation is stable.

        Unlike a single range, a union is closed under intersection, so ``&`` is a total
        operation that never raises.

        Args:
            ranges: the ranges to be joined in a union
        """
        unique: List[MicroarchitectureRange] = []
        for current in ranges:
            if current.empty or current in unique:
                continue
            unique.append(current)

        self.ranges: Tuple[MicroarchitectureRange, ...] = tuple(
            sorted((x for x in unique if not any(x < y for y in unique)), key=str)
        )

        # The known microarchitectures in this union, computed lazily
        self._targets: Optional[FrozenSet[Microarchitecture]] = None

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
        if isinstance(item, str):
            item = Microarchitecture.from_string(item)

        if not isinstance(item, Microarchitecture):
            msg = "only objects of string or Microarchitecture types are accepted [got {0}]"
            raise TypeError(msg.format(str(type(item))))

        return any(item in x for x in self.ranges)

    def __iter__(self) -> Iterator[Microarchitecture]:
        # Same order as MicroarchitectureRange, see the comment there
        return iter(sorted(self._known_targets, key=lambda x: (len(x.ancestors), x.name)))

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
                result.extend(_cover(r1, r2))
        return MicroarchitectureRangeList(result)

    @staticmethod
    def from_string(list_str: str) -> "MicroarchitectureRangeList":
        """Returns a union of microarchitecture ranges from its string representation, which is
        a comma separated list of ranges.

        Raises:
            InvalidRange: if one of the members is not a valid range
            ValueError: if a boundary is not a valid microarchitecture name
        """
        return MicroarchitectureRangeList(
            MicroarchitectureRange.from_string(x) for x in list_str.split(",")
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({list(self.ranges)!r})"

    def __str__(self) -> str:
        if not self.ranges:
            return "{}"
        return ",".join(str(x) for x in self.ranges)


def generic_microarchitecture(name: str) -> Microarchitecture:
    """Returns a generic micro-architecture with no vendor and no features.

    Args:
        name: name of the micro-architecture
    """
    return Microarchitecture(name, parents=[], vendor="generic", features=set(), compilers={})


def version_components(version: str) -> Tuple[str, str]:
    """Decomposes the version passed as input in version number and
    suffix and returns them.

    If the version number or the suffix are not present, an empty
    string is returned.

    Args:
        version: version to be decomposed into its components
    """
    match = re.match(r"([\d.]*)(-?)(.*)", str(version))
    if not match:
        return "", ""

    version_number = match.group(1)
    suffix = match.group(3)

    return version_number, suffix


def _known_microarchitectures():
    """Returns a dictionary of the known micro-architectures. If the
    current host platform is unknown, add it too as a generic target.
    """

    def fill_target_from_dict(name, data, targets):
        """Recursively fills targets by adding the micro-architecture
        passed as argument and all its ancestors.

        Args:
            name (str): micro-architecture to be added to targets.
            data (dict): raw data loaded from JSON.
            targets (dict): dictionary that maps micro-architecture names
                to ``Microarchitecture`` objects
        """
        values = data[name]

        # Get direct parents of target
        parent_names = values["from"]
        for parent in parent_names:
            # Recursively fill parents so they exist before we add them
            if parent in targets:
                continue
            fill_target_from_dict(parent, data, targets)
        parents = [targets.get(parent) for parent in parent_names]

        vendor = values["vendor"]
        features = set(values["features"])
        compilers = values.get("compilers", {})
        generation = values.get("generation", 0)
        cpu_part = values.get("cpupart", "")

        targets[name] = Microarchitecture(
            name, parents, vendor, features, compilers, generation=generation, cpu_part=cpu_part
        )

    known_targets = {}
    data = schema.TARGETS_JSON["microarchitectures"]
    for name in data:
        if name in known_targets:
            # name was already brought in as ancestor to a target
            continue
        fill_target_from_dict(name, data, known_targets)

    # Add the host platform if not present
    host_platform = platform.machine()
    known_targets.setdefault(host_platform, generic_microarchitecture(host_platform))

    return known_targets


#: Dictionary of known micro-architectures
TARGETS = LazyDictionary(_known_microarchitectures)


class ArchspecError(Exception):
    """Base class for errors within archspec"""


class UnsupportedMicroarchitecture(ArchspecError, ValueError):
    """Raised if a compiler version does not support optimization for a given
    micro-architecture.
    """


class InvalidCompilerVersion(ArchspecError, ValueError):
    """Raised when an invalid format is used for compiler versions in archspec."""


class InvalidRange(ArchspecError, ValueError):
    """Raised when an invalid range is constructed."""


class UnknownMicroarchitecture(ArchspecError, ValueError):
    """Raised when a name does not correspond to any known micro-architecture.

    Inherits from ValueError for backward compatibility, so that callers can catch every parsing
    failure with ``except ArchspecError`` without also swallowing unrelated errors.
    """
