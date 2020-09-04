# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""
archspec command line interface
"""

import click
from graphviz import Digraph

import archspec
import archspec.cpu


@click.group(name="archspec")
@click.version_option(version=archspec.__version__)
def main():
    """archspec command line interface"""


def cb_cpu_dag(ctx, param, value):
    """Print Direct Acyclic Graph (DAG) for known CPU microarchitectures."""

    def node_label(uarch):
        """Create node label for specified Microarchitecture instance."""
        res = uarch.name
        if uarch.parents and uarch.vendor != uarch.parents[0].vendor:
            res += " (" + uarch.vendor + ")"
        return res

    cpu_uarch_dag = Digraph()

    for key in archspec.cpu.TARGETS:
        uarch = archspec.cpu.TARGETS[key]
        cpu_uarch_dag.node(uarch.name, node_label(uarch))
        for parent in uarch.parents:
            cpu_uarch_dag.edge(parent.name, uarch.name)

    click.echo(cpu_uarch_dag.source)
    ctx.exit()


def cb_cpu_name(ctx, param, value):
    """Print name of microarchitecture of host CPU."""
    click.echo(archspec.cpu.host())
    ctx.exit()


@main.command()
@click.option('--name', is_flag=True, default=True, callback=cb_cpu_name)
@click.option('--dag', is_flag=True, default=False, callback=cb_cpu_dag)
def cpu():
    """archspec command line interface for CPU"""
