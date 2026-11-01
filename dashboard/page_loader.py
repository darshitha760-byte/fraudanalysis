"""Load dashboard page modules from the dashboard's pages directory."""

import importlib.util
import sys
from pathlib import Path
from typing import Callable


def load_page_main(page_file: str) -> Callable[[], None]:
    """Load a dashboard page by its configured filename and return its main function."""
    dashboard_dir = Path(__file__).resolve().parent
    pages_dir = (dashboard_dir / "pages").resolve()
    page_path = (pages_dir / page_file).resolve()

    if page_path.parent != pages_dir or not page_path.is_file():
        raise FileNotFoundError(f"Dashboard page not found: {page_file}")

    dashboard_path = str(dashboard_dir)
    if dashboard_path not in sys.path:
        sys.path.insert(0, dashboard_path)

    module_name = f"_dashboard_page_{page_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, page_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load dashboard page: {page_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    page_main = getattr(module, "main", None)
    if not callable(page_main):
        raise ImportError(f"Dashboard page has no main() function: {page_file}")
    return page_main
