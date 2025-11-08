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
    Загрузить модуль по path и вернуть callable main (не вызывать его).

    :param path: относительный путь внутри DMP_AF_PYTHON_HOOKS_FOLDER или абсолютный путь до .py файла
    :param hooks_folder_env: имя env-var с папкой hooks (по умолчанию "hooks")
    :param ignore_errors: если True — ошибки логируются и возвращается None, иначе ошибка пробрасывается
    :return: callable main(context=...) или None
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

        module_name = str(file_path)  # используем путь как имя модуля в sys.modules

        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create import spec for {file_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # выполняем код модуля (но не вызываем main)

        # регистрируем модуль под ключом-путём (чтобы избежать конфликтов имён)
        sys.modules[module_name] = module

        main_fn = getattr(module, "main", None)
        if not callable(main_fn):
            raise AttributeError(f"Hook module {file_path!s} does not expose callable 'main(context=...)'")

        return main_fn

    except Exception as exc:  # noqa: BLE001
        msg = f"Failed to load hook {path!r}: {exc!s}"
        if ignore_errors:
            logger.exception(msg)
            return None
        raise
