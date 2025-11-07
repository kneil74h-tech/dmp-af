from pathlib import Path
import importlib.util
import sys
import os
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


def _call_main(module, context: Dict[str, Any]):
    """Найти callable main и вызвать его как main(context=...)."""
    main_fn = getattr(module, "main", None)
    if not callable(main_fn):
        raise AttributeError(f"Module {module!r} does not expose callable 'main(context=...)'")
    return main_fn(context=context)


def load_and_call_hook(
    path: Optional[str],
    context: Optional[Dict[str, Any]] = None,
    *,
    hooks_folder_env: str = "DMP_AF_PYTHON_HOOKS_FOLDER",
    ignore_errors: bool = False,
):
    """
    Динамически импортирует Python-файл и вызывает функцию main(context=...).

    path:
      - относительный путь внутри DMP_AF_PYTHON_HOOKS_FOLDER (по умолчанию "hooks"),
      - или абсолютный путь до .py файла.

    context: dict, передаётся в main(context=...).

    ignore_errors: если True — ошибки логируются и подавляются (возвращается None).
    """
    if not path:
        return None

    context = context or {}

    try:
        file_path = Path(path)
        if not file_path.is_absolute():
            hooks_folder = Path(os.environ.get(hooks_folder_env, "hooks")).resolve()
            file_path = (hooks_folder / path).resolve()

        if not file_path.exists():
            raise FileNotFoundError(f"Hook file not found: {file_path}")

        spec = importlib.util.spec_from_file_location(str(file_path), str(file_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create import spec for {file_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        sys.modules[str(file_path)] = module

        return _call_main(module, context)

    except Exception as exc:  # noqa: BLE001
        msg = f"Failed to load/call hook {path!r}: {exc!s}"
        if ignore_errors:
            logger.exception(msg)
            return None

        raise
