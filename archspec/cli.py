#!/usr/bin/env python

import archspec
import archspec.cpu
import click


@click.group(name="archspec")
def main():
    """archspec command line interface"""
    pass


@main.group()
def cpu():
    """archspec command line interface for CPU"""
    pass


@cpu.command()
def host():
    """print name of CPU microarchitecture of host"""
    click.echo(archspec.cpu.host())


if __name__ == "__main__":
    main()
