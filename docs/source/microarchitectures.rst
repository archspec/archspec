.. Copyright 2020 Lawrence Livermore National Security, LLC and other
   Archspec Project Developers. See the top-level COPYRIGHT file for details.

   SPDX-License-Identifier: (Apache-2.0 OR MIT)

======================
CPU Microarchitectures
======================

A CPU microarchitecture is modeled in ``archspec`` by the
:py:class:`archspec.cpu.Microarchitecture` class.
Objects of this class are constructed automatically to
populate a dictionary of known architectures:

.. code-block:: python

    >>> import archspec.cpu
    >>> archspec.cpu.TARGETS
    <archspec.cpu.schema.LazyDictionary object at 0x7fc7eae49650>

    >>> len(archspec.cpu.TARGETS)
    43

``TARGETS`` maps the names of the microarchitectures to a corresponding
``Microarchitecture`` object in memory:

.. code-block:: python

    >>> archspec.cpu.TARGETS['broadwell']
    Microarchitecture('broadwell', ...)

This dictionary is constructed lazily from data stored in
a JSON file upon the first operation performed on it.

-------------
Basic Queries
-------------

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

If a compiler if unknown to ``archspec`` an empty string is returned:

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
