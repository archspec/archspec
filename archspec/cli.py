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


@main.command()
def cpu():
    """archspec command line interface for CPU"""
    click.echo(archspec.cpu.host())


if __name__ == "__main__":
    main()
