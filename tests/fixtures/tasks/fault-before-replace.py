"""Opt-in isolated-process fault at an OS atomic replacement boundary.

Copied to a temporary sitecustomize.py by one boundary test. This does not import
or patch application functions. Controlled environment paths are owned by that
test; no user files, provider configuration or accounts are accessed.
"""
import os
from pathlib import Path


target = os.environ.get("TASK_TEST_FAULT_TARGET")
marker = os.environ.get("TASK_TEST_FAULT_MARKER")
if target and marker:
    def is_target(destination, options):
        name = os.fsdecode(os.fspath(destination))
        if os.path.isabs(name):
            return os.path.abspath(name) == target
        descriptor = options.get("dst_dir_fd")
        if descriptor is None:
            return os.path.abspath(name) == target
        parent = os.stat(Path(target).parent)
        actual = os.fstat(descriptor)
        return (actual.st_dev, actual.st_ino) == (parent.st_dev, parent.st_ino) and name == Path(target).name

    def instrument(original):
        def interrupted(source, destination, *args, **kwargs):
            if is_target(destination, kwargs):
                Path(marker).write_text("crashed-before-atomic-replace\n", encoding="utf-8")
                os._exit(86)
            return original(source, destination, *args, **kwargs)
        return interrupted
    os.replace = instrument(os.replace)
    os.rename = instrument(os.rename)
