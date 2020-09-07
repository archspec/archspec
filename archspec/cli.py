# Copyright 2019-2020 Lawrence Livermore National Security, LLC and other
# Archspec Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""
archspec command line interface
"""

import click
import graphviz

import archspec
import archspec.cpu


@click.group(name="archspec")
@click.version_option(version=archspec.__version__)
def main():
    """archspec command line interface"""


@main.command()
def cpu():
    """archspec command line interface for CPU"""
    click.echo(archspec.cpu.host())


@main.command()
@click.option(
    "--cpu",
    "only_cpu",
    is_flag=True,
    default=False,
    help="Only print DAG for CPU microarchitectures",
)
def graph(only_cpu):
    """Print Direct Acyclic Graph (DAG) for all known system aspects."""

    def node_label(uarch):
        """Create node label for specified Microarchitecture instance."""
        res = uarch.name
        if uarch.parents and uarch.vendor != uarch.parents[0].vendor:
            res += " (" + uarch.vendor + ")"
        return res

    # for now only CPU microarchitectures are supported so this looks a bit silly,
    # but eventually the idea is to only print all aspects if no specific aspect was selected
    if not only_cpu:
        all_aspects = True

    if only_cpu or all_aspects:
        cpu_uarch_dag = graphviz.Digraph()

        for uarch in archspec.cpu.TARGETS.values():
            cpu_uarch_dag.node(uarch.name, node_label(uarch))
            for parent in uarch.parents:
                cpu_uarch_dag.edge(parent.name, uarch.name)

        click.echo(cpu_uarch_dag.source)
