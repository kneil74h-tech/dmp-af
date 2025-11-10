import sys
from pathlib import Path
import pytest

from dmp_af.common.hooks import load_and_get_main_callable


def _cleanup_module(file_path: Path):
    sys.modules.pop(str(file_path), None)


def test_loads_callable_and_executes(tmp_path, monkeypatch):
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    monkeypatch.setenv("DMP_AF_PYTHON_HOOKS_FOLDER", str(hooks_dir))

    hook_file = hooks_dir / "pre_hook.py"
    hook_file.write_text(
        "def main(context):\n"
        "    return context.get('x')\n"
    )

    try:
        main_fn = load_and_get_main_callable("pre_hook.py")
        assert callable(main_fn)
        assert main_fn({"x": 123}) == 123
    finally:
        _cleanup_module(hook_file)


def test_module_is_not_reexecuted_on_second_load(tmp_path, monkeypatch):
    """
    Verify that calling load_and_get_main_callable twice for the same file
    does not re-execute the module code (it is reused from sys.modules).
    On the first import, COUNTER == 1; on the second import, it remains 1.
    """
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    monkeypatch.setenv("DMP_AF_PYTHON_HOOKS_FOLDER", str(hooks_dir))

    hook_file = hooks_dir / "counter_hook.py"
    hook_file.write_text(
        "try:\n"
        "    COUNTER\n"
        "except NameError:\n"
        "    COUNTER = 0\n"
        "COUNTER = COUNTER + 1\n"
        "def main(context):\n"
        "    return COUNTER\n"
    )

    try:
        first = load_and_get_main_callable("counter_hook.py")
        assert first is not None
        assert first({}) == 1

        second = load_and_get_main_callable("counter_hook.py")
        assert second is not None

        assert first is second
        assert second({}) == 1
    finally:
        _cleanup_module(hook_file)


def test_missing_file_raises_or_ignored(tmp_path, monkeypatch):
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    monkeypatch.setenv("DMP_AF_PYTHON_HOOKS_FOLDER", str(hooks_dir))

    with pytest.raises(FileNotFoundError):
        load_and_get_main_callable("no_such_hook.py")

    assert load_and_get_main_callable("no_such_hook.py", ignore_errors=True) is None


def test_main_not_callable_raises_or_ignored(tmp_path, monkeypatch):
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    monkeypatch.setenv("DMP_AF_PYTHON_HOOKS_FOLDER", str(hooks_dir))

    hook_file = hooks_dir / "bad_hook.py"
    hook_file.write_text(
        "main = 12345\n"
    )

    try:
        with pytest.raises(AttributeError):
            load_and_get_main_callable("bad_hook.py")

        assert load_and_get_main_callable("bad_hook.py", ignore_errors=True) is None
    finally:
        _cleanup_module(hook_file)
