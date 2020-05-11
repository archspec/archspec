#!/usr/bin/env python
"""
archspec command line interface
"""

import click

import archspec
import archspec.cpu


@click.group(name="archspec")
def main():
    """archspec command line interface"""


@main.group()
def cpu():
    """archspec command line interface for CPU"""


@cpu.command()
def host():
    """print name of CPU microarchitecture of host"""
    click.echo(archspec.cpu.host())


if __name__ == "__main__":
    main()
