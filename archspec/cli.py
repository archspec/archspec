#!/usr/bin/env python

import archspec
import archspec.cpu
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="archspec command line interface", prog='archspec')

    parser.add_argument('--cpu-host', help="Print name of host CPU microarchitecture", action='store_true')
    parser.add_argument('--version', action='version', version=archspec.__version__)

    args = parser.parse_args()

    if args.cpu_host:
        print(archspec.cpu.host())
        sys.exit(0)
    else:
        parser.print_usage()
        sys.exit(1)


if __name__ == '__main__':
    main()
