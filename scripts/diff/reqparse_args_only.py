"""Replaces the fork's QueryArgument with the args-only variant (spike spec §6, fix 3 as first written), for comparison runs.

Usage: python reqparse_args_only.py <path to bigchaindb/web/views/base.py>   (edits a scratch copy in a container)
"""
import re
import sys

path = sys.argv[1]
source = open(path).read()
variant = '''class QueryArgument(reqparse.Argument):
    def __init__(self, *args, location='args', **kwargs):
        super().__init__(*args, location=location, **kwargs)


def make_error('''
patched, count = re.subn(r'class QueryArgument\(reqparse\.Argument\):.*?\ndef make_error\(', variant, source, flags=re.S)
assert count == 1, 'QueryArgument not found'
open(path, 'w').write(patched)
