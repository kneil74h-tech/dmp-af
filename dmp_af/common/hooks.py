from pathlib import Path
import importlib.util
import sys
import os
from typing import Optional, Dict, Any, Callable
import logging

logger = logging.getLogger(__name__)


def load_and_get_main_callable(
    path: Optional[str],
    *,
    hooks_folder_env: str = "DMP_AF_PYTHON_HOOKS_FOLDER",
    ignore_errors: bool = False,
) -> Optional[Callable[[Dict[str, Any]], Any]]:
    """
    Load a Python module from the given path and return its callable `main` function.

    :param path: Relative path inside the hooks folder or absolute path to a .py file.
    :param hooks_folder_env: Environment variable name pointing to the hooks folder (default: "DMP_AF_PYTHON_HOOKS_FOLDER").
    :param ignore_errors: If True, log errors and return None instead of raising.
    :return: Callable `main(context: dict)` from the loaded module, or None if loading fails.
    """
    if not path:
        return None

    try:
        file_path = Path(path)
        if not file_path.is_absolute():
            hooks_folder = Path(os.environ.get(hooks_folder_env, "hooks")).resolve()
            file_path = (hooks_folder / path).resolve()

        if not file_path.exists():
            raise FileNotFoundError(f"Hook file not found: {file_path}")

        module_key = str(file_path)

        if module_key in sys.modules:
            module = sys.modules[module_key]
        else:
            spec = importlib.util.spec_from_file_location(module_key, str(file_path))
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create import spec for {file_path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sys.modules[module_key] = module

        main_fn = getattr(module, "main", None)
        if not callable(main_fn):
            raise AttributeError(f"Hook module {file_path!s} does not expose callable 'main'")

        return main_fn

    except Exception as exc:  # noqa: BLE001
        msg = f"Failed to load hook {path!r}: {exc!s}"
        if ignore_errors:
            logger.exception(msg)
            return None
        raise
