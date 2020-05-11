#!/usr/bin/env python

import archspec
import archspec.cpu
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="archspec command line interface",
                                     prog='archspec')
    parser.add_argument('-V', '--version', action='version', version=archspec.__version__)

    subparsers = parser.add_subparsers()

    cpu_parser = subparsers.add_parser('cpu')

    cpu_host_parser = cpu_parser.add_subparsers().add_parser('host')
    cpu_host_parser.add_argument('cpu.host', help="print name of host CPU microarchitecture",
                                 action='store_true')

    args = parser.parse_args()

    if getattr(args, 'cpu.host'):
        print(archspec.cpu.host())
        sys.exit(0)
    else:
        parser.print_usage()
        sys.exit(1)


if __name__ == '__main__':
    main()
