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
