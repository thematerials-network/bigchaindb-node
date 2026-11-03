"""Prints every difference between two JSON result files (run_corpus.py, http_diff.py, ws_diff.py output).

Usage: python compare.py <old.json> <new.json> [--ignore <top-level key>]...
Exit code 1 if anything differs.
"""
import json
import sys


def shorten(value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= 300 else text[:300] + '…'


def walk(path, old, new, out):
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            if key not in old:
                out.append((path + '/' + key, '<missing>', shorten(new[key])))
            elif key not in new:
                out.append((path + '/' + key, shorten(old[key]), '<missing>'))
            else:
                walk(path + '/' + key, old[key], new[key], out)
    elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for index, (old_item, new_item) in enumerate(zip(old, new)):
            walk('%s[%d]' % (path, index), old_item, new_item, out)
    elif old != new:
        out.append((path, shorten(old), shorten(new)))


def main():
    args = sys.argv[1:]
    ignored = set()
    while '--ignore' in args:
        index = args.index('--ignore')
        ignored.add(args[index + 1])
        del args[index:index + 2]
    old, new = (json.load(open(path)) for path in args)
    for key in ignored:
        old.pop(key, None)
        new.pop(key, None)
    differences = []
    walk('', old, new, differences)
    for path, old_value, new_value in differences:
        print(path)
        print('  old:', old_value)
        print('  new:', new_value)
    print('%d difference(s)' % len(differences))
    sys.exit(1 if differences else 0)


if __name__ == '__main__':
    main()
