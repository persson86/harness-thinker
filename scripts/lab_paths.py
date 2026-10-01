"""Validate lab boundaries using filesystem identity as well as path spelling."""
import json
import os
from pathlib import Path


def canonical(path):
    path = Path(path).expanduser().absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("Use canonical paths without symlinks")
    return path.resolve()


def _within(path, root):
    if path == root or root in path.parents:
        return True
    try:
        identity = root.stat()
    except FileNotFoundError:
        return False
    # Case and Unicode aliases can have different spellings on APFS while
    # resolving to the same inode. Include existing ancestors of new paths.
    for part in (path, *path.parents):
        try:
            current = part.stat()
        except FileNotFoundError:
            continue
        if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
            return True
    return False


def overlap(a, b):
    a, b = Path(a), Path(b)
    return _within(a, b) or _within(b, a)


def protected_paths(paths):
    if not isinstance(paths, (list, tuple)) or not paths:
        raise ValueError("Explicit protected roots are required")
    result = []
    for value in paths:
        if not isinstance(value, (str, os.PathLike)):
            raise ValueError("Invalid protected root")
        path = canonical(value)
        if not path.is_dir():
            raise ValueError("Protected roots must be existing directories")
        result.append(path)
    return result


def load_lab(root, marker="thinker-lab.json"):
    root = canonical(root)
    path = root / marker
    if path.is_symlink():
        raise ValueError("Invalid lab marker")
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or config.get("schema") != 1 or config.get("root") != str(root):
        raise ValueError("Unrecognized lab")
    for protected in protected_paths(config.get("protected_roots")):
        if overlap(root, protected):
            raise ValueError("Lab overlaps protected root")
    return root, config
