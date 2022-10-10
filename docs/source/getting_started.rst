.. Copyright 2020 Lawrence Livermore National Security, LLC and other
   Archspec Project Developers. See the top-level COPYRIGHT file for details.

   SPDX-License-Identifier: (Apache-2.0 OR MIT)

===============
Getting Started
===============

Archspec is a minimal-size python package that makes it easier to work with
various aspects of a system architecture like CPU, network fabrics, etc.
by providing:

* A set of human-understandable names for each entity
* Well defined APIs to query properties from objects or compare them


.. note::

    This project grew out of `Spack <https://spack.io/>`_ and is currently
    under active development. At present it only models CPU
    microarchitectures but extensions to other aspects are expected in the future.


---------------------
Software requirements
---------------------

Archspec needs the following software:

.. list-table::
    :align: center

    * - Python
      - 2.7 or 3.5+
    * - `six <https://pypi.org/project/six/>`_
      - ^1.13.0
    * - `click <https://click.palletsprojects.com/en/7.x/>`_
      - >=7.1.2

It is a multiplatform project and currently works on linux and MacOS.
Porting to Windows is expected in the future.

----------------------
Installation from PyPI
----------------------

Archspec is published on `PyPI <https://pypi.org/>`_ so to install
any release you can simply use ``pip``:

.. code-block:: console

    $ pip install archspec[==<required-release>]
    $ python -c "import archspec; print(archspec.__version__)"
    0.1.4

This is the simplest way to install the package and getting
started using it.

---------------------------------
Installing from GitHub repository
---------------------------------

Installing Archspec from a clone of its GitHub Repository
requires `poetry <https://python-poetry.org/>`_. The
preferred method to install this tool is via
its custom installer outside of any virtual environment:

.. code-block:: console

    $ curl -sSL https://install.python-poetry.org | python3 -

You can refer to `Poetry's documentation <https://python-poetry.org/docs/#installation>`_
for further details or for other methods to install it.
Once ``poetry`` is available we can proceed with cloning the repository
and installing Archspec:

.. code-block:: console

    $ which poetry
    /home/user/.poetry/bin/poetry

    $ git clone --recursive https://github.com/archspec/archspec.git
    $ cd archspec

    $ poetry install --no-dev
    Creating virtualenv archspec-0fr1r4aA-py2.7 in /home/culpo/.cache/pypoetry/virtualenvs
    Updating dependencies
    Resolving dependencies... (17.7s)

    Writing lock file


    Package operations: 2 installs, 0 updates, 0 removals

      - Installing click (7.1.2)
      - Installing six (1.15.0)
      - Installing archspec (0.1.4)

    $ poetry run python -c "import archspec; print(archspec.__version__)"
    0.1.4

Poetry manages virtual environments for the user. Using ``poetry run`` is
just one of the possibility offered by this tool, for further options
you can refer to `its documentation <https://python-poetry.org/docs>`_.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Install Development Dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To install Archspec with its development dependencies you just
need to omit the ``--no-dev`` option from the commands shown
above:

.. code-block:: console

    $ git clone --recursive https://github.com/archspec/archspec.git
    $ cd archspec

    $ poetry install
    Installing dependencies from lock file


    Package operations: 21 installs, 0 updates, 0 removals

      [...]
      - Installing pytest (4.6.9)
      - Installing jsonschema (3.2.0)
      - Installing pytest-cov (2.8.1)
      - Installing archspec (0.1.4)

At this point you can run unit-tests, linters or other checks. When
developing we recommend to use Python ^3.6 so that the latest versions
of each development tool can be used:

.. code-block:: console

    $ poetry run pytest
    ============================================================== test session starts ===============================================================
    platform linux -- Python 3.7.6, pytest-5.3.4, py-1.8.1, pluggy-0.13.1
    rootdir: /home/culpo/tmp/archspec/docs-scratch/archspec
    plugins: cov-2.8.1
    collected 255 items

    tests/test_archspec.py .                                                                                                                   [  0%]
    tests/test_cpu.py ........................................................................................................................ [ 47%]
    ......................................................................................................................................     [100%]

    ============================================================== 255 passed in 0.73s ===============================================================

    $ poetry run black --check archspec tests
    All done! ✨ 🍰 ✨
    9 files would be left unchanged.

    $ poetry run pylint archspec
    --------------------------------------------------------------------
    Your code has been rated at 10.00/10 (previous run: 10.00/10, +0.00)

