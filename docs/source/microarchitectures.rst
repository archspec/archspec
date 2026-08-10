.. Copyright 2020 Lawrence Livermore National Security, LLC and other
   Archspec Project Developers. See the top-level COPYRIGHT file for details.

   SPDX-License-Identifier: (Apache-2.0 OR MIT)

======================
CPU microarchitectures
======================

The primary goal of ``archspec`` is to be able to detect and label CPU microarchitectures
at a granularity that allows reasoning about binary compatibility. Using this library a client
can:

1. Detect the microarchitecture of the current host, and compare it to a label on a binary
   to determine whether they are compatible.
2. Check if a particular microarchitecture supports a given feature
3. Retrieve the flags to use for a particular compiler to build a binary specifically for
   a microarchitecture


.. _cpu_json_database:

-------------
JSON database
-------------

All the *static knowledge* of microarchitecture names, features, compiler support
etc. is stored in a JSON file. The most important information there is
the dictionary of known microarchitectures. An example record in this dictionary looks like:

.. code-block:: json

   "sandybridge": {
      "from": ["westmere"],
      "vendor": "GenuineIntel",
      "features": [
        "mmx",
        "sse",
        "sse2",
        "ssse3",
        "sse4_1",
        "sse4_2",
        "popcnt",
        "aes",
        "pclmulqdq",
        "avx"
      ],
      "compilers": {
        "gcc": [
          {
            "versions": "4.9:",
            "flags": "-march={name} -mtune={name}"
          },
          {
            "versions": "4.6:4.8.5",
            "name": "corei7-avx",
            "flags": "-march={name} -mtune={name}"
          }
        ],
      }
    },

Each entry maps a unique, human-readable, label to corresponding information on:

- The closest compatible microarchitecture
- The vendor of the microarchitecture
- The features that are available
- The optimization support provided by compilers

The granularity of the labels follow those used by compilers to emit processor-specific
instructions, but the actual labels might differ a bit to enhance their readability
(e.g. ``archspec`` refers to the ``steamroller`` microarchitecture as opposed to ``bdver3``).
On top of this static information ``archspec`` provides language bindings with logic to
detect, query and compare different microarchitectures.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^
User specified JSON database
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Users have two ways to customize the JSON files of ``archspec``. They can either set the ``ARCHSPEC_CPU_DIR``
environment variable to a directory where they provide a *complete replacement* of all the JSON files expected
by the package, or they can set the ``ARCHSPEC_EXTENSION_CPU_DIR`` environment variable to a directory where
they can prepare JSON files containing only the items they need to add or override.

In the latter case, the update of the default JSON files is done on the top-level attribute. This means, for
instance, that a JSON file to add or override the ``pentium2`` architecture looks like the following:

.. code-block:: json

   {
     "microarchitectures": {
       "pentium2": {
         "from": ["i686"],
         "vendor": "GenuineIntel",
         "features": [
           "mmx"
         ]
       }
     }
   }

This feature might be helpful when working with unreleased hardware, or when using virtualized environments
that don't provide the same CPU flags as their corresponding bare metal counterpart.

.. _cpu_host_detection:

--------------
Host detection
--------------

Detection of the host where ``archspec`` is being run can be performed with a simple function call:

.. code-block:: python

   >>> import archspec.cpu
   >>> host = archspec.cpu.host()

where the return value is a :py:class:`archspec.cpu.Microarchitecture` object. To obtain the
label of the host one can simply convert this object to a string:

.. code-block:: python

   >>> str(host)
   'cannonlake'

If more information is needed the object can also be converted to a built-in dictionary:

.. code-block:: python

   >>> import pprint
   >>> pprint.pprint(host.to_dict())
   {'features': ['adx',
                 'aes',
                 'avx',
                 'avx2',
                 'avx512bw',
                 'avx512cd',
                 'avx512dq',
                 'avx512f',
                 'avx512ifma',
                 'avx512vbmi',
                 'avx512vl',
                 'bmi1',
                 'bmi2',
                 'clflushopt',
                 'f16c',
                 'fma',
                 'mmx',
                 'movbe',
                 'pclmulqdq',
                 'popcnt',
                 'rdrand',
                 'rdseed',
                 'sha',
                 'sse',
                 'sse2',
                 'sse4_1',
                 'sse4_2',
                 'ssse3',
                 'umip',
                 'xsavec',
                 'xsaveopt'],
    'generation': 0,
    'name': 'cannonlake',
    'parents': ['skylake'],
    'vendor': 'GenuineIntel'}

.. _cpu_microarchitecture_object:

----------------------
Queries and comparison
----------------------

The list of all microarchitectures known by ``archspec`` is accessible through a global dictionary
that maps the microarchitecture labels to a corresponding ``Microarchitecture`` object in memory:

.. code-block:: python

    >>> import archspec.cpu
    >>> archspec.cpu.TARGETS
    <archspec.cpu.schema.LazyDictionary object at 0x7fc7eae49650>

    >>> archspec.cpu.TARGETS['broadwell']
    Microarchitecture('broadwell', ...)

    >>> len(archspec.cpu.TARGETS)
    43

This dictionary is constructed lazily from data stored in the :ref:`cpu_json_database`
upon the first operation performed on it (e.g. the :ref:`cpu_host_detection` shown
in the previous section).
A ``Microarchitecture`` object can be queried for its name and vendor:

.. code-block:: python

    >>> uarch = archspec.cpu.TARGETS['broadwell']
    >>> uarch.name
    'broadwell'

    >>> uarch.vendor
    'GenuineIntel'

All the names used for microarchitectures are intended to be *human-understandable*
and to capture an entire class of chips that have the same capabilities. A
microarchitecture can also be queried for features:

.. code-block:: python

    >>> 'avx' in archspec.cpu.TARGETS['broadwell']
    True
    >>> 'avx' in archspec.cpu.TARGETS['thunderx2']
    False
    >>> 'neon' in archspec.cpu.TARGETS['thunderx2']
    True

since they implement a "container" semantic that is meant to
indicate which cpu features they support. The verbatim list of
features for each object is stored in the ``features``
attribute:

.. code-block:: python

    >>> archspec.cpu.TARGETS['nehalem'].features
    {'sse2', 'sse', 'ssse3', 'sse4_1', 'mmx', 'sse4_2', 'popcnt'}

    >>> archspec.cpu.TARGETS['thunderx2'].features
    {'fp', 'cpuid', 'aes', 'sha2', 'crc32', 'pmull', 'sha1', 'atomics', 'evtstrm', 'asimd', 'asimdrdm'}

    >>> archspec.cpu.TARGETS['power9le'].features
    set()

Usually the semantic of this field varies according to the CPU that is modeled.
For instance Intel tend to list all the features of a chip in that field, while ARM list only
the flags that have been added on top of the base model. Given a microarchitecture we can
query its direct parents or the entire list of ancestors:

.. code-block:: python

    >>> archspec.cpu.TARGETS['nehalem'].parents
    [Microarchitecture('core2', ...)]

    >>> archspec.cpu.TARGETS['nehalem'].ancestors
    [Microarchitecture('core2', ...), Microarchitecture('nocona', ...), Microarchitecture('x86_64', ...)]

Parenthood in this context is considered by CPU features and not chronologically. This
way each architecture is compatible with its parents i.e. binaries running on the
parents can be run on the current microarchitecture. Following the list of ancestors
we can arrive at the root of the DAG that models a given microarchitecture:

.. code-block:: python

    >>> archspec.cpu.TARGETS['nehalem'].ancestors[-1]
    Microarchitecture('x86_64', ...)

The same result can be achieved using the ``family`` attribute:

.. code-block:: python

    >>> archspec.cpu.TARGETS['nehalem'].family
    Microarchitecture('x86_64', ...)

since the returned object represents the "family architecture" i.e. the lowest
common denominator of all the microarchitectures in the DAG. Finally, modeling
microarchitectures as DAGs permits to implement set comparison among them:

.. code-block:: python

    >>> archspec.cpu.TARGETS['nehalem'] < archspec.cpu.TARGETS['broadwell']
    True

    >>> archspec.cpu.TARGETS['nehalem'] == archspec.cpu.TARGETS['broadwell']
    False

    >>> archspec.cpu.TARGETS['nehalem'] > archspec.cpu.TARGETS['broadwell']
    False

    >>> archspec.cpu.TARGETS['nehalem'] > archspec.cpu.TARGETS['a64fx']
    False

.. _cpu_microarchitecture_ranges:

------------------------------
Ranges of microarchitectures
------------------------------

Since microarchitectures are ordered, a client can express a constraint like "``broadwell``
or better, up to ``skylake``" as a range, instead of enumerating every microarchitecture that
satisfies it. A ``MicroarchitectureRange`` holds every microarchitecture between a lower and an
upper boundary, and can be built from a string:

.. code-block:: python

    >>> import archspec.cpu
    >>> archspec.cpu.MicroarchitectureRange.from_string('broadwell:skylake')
    MicroarchitectureRange(lo=Microarchitecture('broadwell'), hi=Microarchitecture('skylake'))

Either boundary can be omitted. A missing upper boundary leaves the range open, so it also
matches microarchitectures added to the :ref:`cpu_json_database` in the future, while a missing
lower boundary is normalized to the family of the upper one:

.. code-block:: python

    >>> str(archspec.cpu.MicroarchitectureRange.from_string(':skylake'))
    'x86_64:skylake'

A bare name is the range holding that microarchitecture only, and a range whose boundaries
coincide is rendered back as a bare name:

.. code-block:: python

    >>> str(archspec.cpu.MicroarchitectureRange.from_string('broadwell'))
    'broadwell'

A range always holds at least its own lower boundary, so it is never empty. Constructing one
without any boundary is an error, and so is asking for the empty set in string form:

.. code-block:: python

    >>> archspec.cpu.MicroarchitectureRange()
    Traceback (most recent call last):
      File "<input>", line 1, in <module>
    archspec.cpu.microarchitecture.InvalidRange: a range needs at least one boundary; the empty set of microarchitectures is an empty MicroarchitectureRangeList

The empty set is a state a client can reach, but not one it can spell; see
`Unions of ranges`_ below.

A range can also be built from its boundaries directly, given either as names or as
``Microarchitecture`` objects, and implements a "container" semantic over microarchitectures:

.. code-block:: python

    >>> uarch_range = archspec.cpu.MicroarchitectureRange(lo='broadwell', hi='skylake')
    >>> 'broadwell' in uarch_range
    True
    >>> 'skylake' in uarch_range
    True
    >>> 'zen2' in uarch_range
    False

Note that ``haswell`` is *not* in the range above, since it is an ancestor of ``broadwell`` and
therefore below the lower boundary. Because the boundaries follow the DAG rather than a release
timeline, a range only ever holds microarchitectures on the paths between them:

.. code-block:: python

    >>> [str(x) for x in archspec.cpu.MicroarchitectureRange(lo='broadwell', hi='cascadelake')]
    ['broadwell', 'skylake', 'skylake_avx512', 'cascadelake']

Iteration is stable, and always yields the most generic microarchitectures first. ``cannonlake``
is missing from that list even though it descends from ``skylake``, because it sits on the other
side of a bifurcation and is not an ancestor of ``cascadelake``:

.. code-block:: python

    >>> 'cannonlake' in archspec.cpu.MicroarchitectureRange(lo='broadwell', hi='cascadelake')
    False

One range can be compared to another with set semantics, to check whether it is entirely
contained in it:

.. code-block:: python

    >>> narrow = archspec.cpu.MicroarchitectureRange(lo='broadwell', hi='icelake')
    >>> wide = archspec.cpu.MicroarchitectureRange(lo='x86_64_v2')
    >>> narrow <= wide
    True
    >>> wide <= narrow
    False

Ranges are compared by their boundaries, and not by the microarchitectures they happen to hold
today, so that comparisons stay stable as the JSON database grows. Two ranges can also be
incomparable, since containment is a partial order.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Why a single range is not closed under set algebra
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A range deliberately offers neither ``|`` nor ``&``:

.. code-block:: python

    >>> r1 = archspec.cpu.MicroarchitectureRange(lo='armv8.6a')
    >>> r2 = archspec.cpu.MicroarchitectureRange(lo='neoverse_n1')
    >>> r1 & r2
    Traceback (most recent call last):
      File "<input>", line 1, in <module>
    TypeError: unsupported operand type(s) for &: 'MicroarchitectureRange' and 'MicroarchitectureRange'

The reason is that microarchitectures form a partial order, but **not a lattice**: two of them
need not have a unique closest common ancestor or descendant. When that happens the intersection
of two ranges is a perfectly well-defined *set* of microarchitectures that has no unique
boundary, and so is not a range at all.

The pair above is the canonical case. ``armv8.6a`` and ``neoverse_n1`` are not comparable, and
the microarchitectures above both of them are ``ampere1`` and ``ampere1a``, which are not
comparable either, so the result has two minimal elements instead of one. Swapping the
boundaries gives the mirror case, where the microarchitectures below both ``ampere1`` and
``ampere1a`` have two maximal elements.

Union has the same problem, more obviously: two ranges from different architecture families
have nothing in between to interpolate over.

Rather than offer an operation that fails on some inputs, or one that silently widens or narrows
the answer, both operations live on the union type described below, where they are total. In the
currently modeled data every such pair is in the ``aarch64`` family, coming from the
``ampere1``/``ampere1a`` pair and the ``neoverse`` chips each having two parents; the ``x86_64``
family is a lattice. Note that a bifurcation on its own is not a problem: ``cascadelake`` and
``cannonlake`` are not comparable, but ``icelake`` descends from both and ``skylake`` precedes
both, so their boundaries stay unambiguous.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Unions of ranges
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A ``MicroarchitectureRangeList`` is a union of ranges, written as a comma separated list. It is
what a client needs when a constraint cannot be expressed as a single interval, for instance
because it spans two architecture families:

.. code-block:: python

    >>> str(archspec.cpu.MicroarchitectureRangeList.from_string('x86_64_v2:skylake,zen4:'))
    'x86_64_v2:skylake,zen4:'

Members are normalized on construction: duplicates and members contained in another member are
dropped, and what is left is sorted, so that the string representation is stable and can be
parsed back:

.. code-block:: python

    >>> str(archspec.cpu.MicroarchitectureRangeList.from_string('x86_64:,broadwell:skylake'))
    'x86_64:'

A union holds the microarchitectures of all its members, and can be compared to another union
with the same set semantics as a single range.

A bare ``:`` is accepted as a shorthand for *every* microarchitecture. Since the families are
disjoint this is never a single range, but it is a perfectly good union, with one open range per
family:

.. code-block:: python

    >>> str(archspec.cpu.MicroarchitectureRangeList.from_string(':'))
    'aarch64:,arm:,ppc64:,ppc64le:,ppc:,ppcle:,riscv64:,sparc64:,sparc:,x86:,x86_64:'

Note that this is a shorthand for input, and not a canonical form: it renders back as the
explicit list above, and it covers the families present in the :ref:`cpu_json_database` when it
is parsed. It is also only recognized as the whole string, never as one member of a comma
separated list.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The empty set
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A union with no members is the empty set of microarchitectures, and since a range is never empty
it is the only representation for it. A client reaches it by asking for it, or by narrowing a
constraint down to nothing:

.. code-block:: python

    >>> ranges = archspec.cpu.MicroarchitectureRangeList
    >>> ranges().empty
    True
    >>> str(ranges.from_string('broadwell:') & ranges.from_string('aarch64:'))
    '{}'

The ``{}`` is a display marker, so that an unsatisfiable result stays visible when it is
interpolated into a message. It is deliberately **not** part of the string grammar, the same way
there is no way to write an empty version range in a Spack spec:

.. code-block:: python

    >>> ranges.from_string('{}')
    Traceback (most recent call last):
      File "<input>", line 1, in <module>
    archspec.cpu.microarchitecture.InvalidRange: the empty set of microarchitectures has no string representation, and can only be built as an empty MicroarchitectureRangeList

The empty set and the ``:`` shorthand above are therefore the two values for which the
round trip through ``str`` does not hold.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Set algebra on unions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The reason for having this type is that, unlike a single range, a union *is* closed under both
operations, so ``|`` and ``&`` are **total** and never raise. Union is the straightforward one,
since it only has to join the members and let normalization do the rest:

.. code-block:: python

    >>> l1 = archspec.cpu.MicroarchitectureRangeList.from_string('broadwell:skylake')
    >>> l2 = archspec.cpu.MicroarchitectureRangeList.from_string('zen4:')
    >>> str(l1 | l2)
    'broadwell:skylake,zen4:'

    >>> str(l1 | archspec.cpu.MicroarchitectureRangeList.from_string('x86_64:'))
    'x86_64:'

Intersection is the interesting one. It is defined on the pair from the previous section, which a
single range cannot express:

.. code-block:: python

    >>> l1 = archspec.cpu.MicroarchitectureRangeList.from_string('armv8.6a:')
    >>> l2 = archspec.cpu.MicroarchitectureRangeList.from_string('neoverse_n1:')
    >>> str(l1 & l2)
    'ampere1:,ampere1a:'

The two minimal elements that leave the lower boundary ambiguous become two members of the union.
When the intersection does have unique boundaries, the result is the single range between them,
so a union only ever grows extra members where it has to:

.. code-block:: python

    >>> l1 = archspec.cpu.MicroarchitectureRangeList.from_string('skylake:icelake')
    >>> l2 = archspec.cpu.MicroarchitectureRangeList.from_string('x86_64_v2:cascadelake')
    >>> str(l1 & l2)
    'skylake:cascadelake'

An intersection is exact over the *known* microarchitectures, which is the same caveat that
iteration over a range already carries. A microarchitecture added to the
:ref:`cpu_json_database` in the future, descending from both ``armv8.6a`` and ``neoverse_n1``
but from neither ``ampere1`` nor ``ampere1a``, would fall inside the intersection without being
covered by any of the members above. A union carries no such caveat, since it never has to
recompute a boundary.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Recovering a single microarchitecture
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A client that narrows a constraint down usually wants to know when only one microarchitecture is
left, and to get that object back. Both a range and a union expose a ``concrete`` property, which
returns the microarchitecture when the boundaries denote exactly one, and ``None`` otherwise:

.. code-block:: python

    >>> r1 = archspec.cpu.MicroarchitectureRangeList.from_string('x86_64:skylake')
    >>> r2 = archspec.cpu.MicroarchitectureRangeList.from_string('skylake:icelake')
    >>> (r1 & r2).concrete
    Microarchitecture('skylake')

The object returned is the one from :py:data:`archspec.cpu.TARGETS`, so features, vendor and
compiler information are all still reachable through it.

Note that this is deliberately *not* the same question as whether the range holds one
microarchitecture today. ``mic_knl`` is concrete, while ``mic_knl:`` is not, even though
``mic_knl`` currently has no descendant and both enumerate a single microarchitecture:

.. code-block:: python

    >>> ranges = archspec.cpu.MicroarchitectureRangeList
    >>> len(ranges.from_string('mic_knl:'))
    1
    >>> ranges.from_string('mic_knl:').concrete is None
    True
    >>> str(ranges.from_string('mic_knl').concrete)
    'mic_knl'

Use ``concrete`` rather than ``len(...) == 1`` for this, so that adding a descendant of
``mic_knl`` to the database does not silently change what the client concludes.

-----------------------------
Compiler's Optimization Flags
-----------------------------

Another information that each microarchitecture object has available is
which compiler flags needs to be used to emit code optimized for itself:

.. code-block:: python

    >>> archspec.cpu.TARGETS['broadwell'].optimization_flags('intel', '19.0.1')
    '-march=broadwell -mtune=broadwell'

Sometimes compiler flags change across versions of the same compiler:

.. code-block:: python

    >>> archspec.cpu.TARGETS['thunderx2'].optimization_flags('gcc', '9.1.0')
    '-mcpu=thunderx2t99'

    >>> archspec.cpu.TARGETS['thunderx2'].optimization_flags('gcc', '5.1.0')
    '-march=armv8-a+crc+crypto'

If a compiler is unknown to ``archspec`` an empty string is returned:

.. code-block:: python

    >>> archspec.cpu.TARGETS['broadwell'].optimization_flags('unknown', '5.1')
    ''

while if a compiler is known to **not be able to optimize** for a given
architecture an exception is raised:

.. code-block:: python

    >>> archspec.cpu.TARGETS['icelake'].optimization_flags('gcc', '4.8.3')
    Traceback (most recent call last):
      File "<input>", line 1, in <module>
      File "/home/user/PycharmProjects/archspec/archspec/cpu/microarchitecture.py", line 282, in optimization_flags
        raise UnsupportedMicroarchitecture(msg)
    archspec.cpu.microarchitecture.UnsupportedMicroarchitecture: cannot produce optimized binary for micro-architecture 'icelake' with gcc@4.8.3 [supported compiler versions are 8.0:]
