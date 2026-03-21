__version__ = "0.1.0"


def ensure_dependency(package: str, import_name: str | None = None):
    """Import a package, auto-installing it via pip if missing.

    Args:
        package: The pip package name (e.g. "feedparser").
        import_name: The Python import name if different from the pip name.
    """
    import importlib
    mod_name = import_name or package
    try:
        return importlib.import_module(mod_name)
    except ImportError:
        import subprocess
        import sys
        print(f"  Installing missing dependency: {package}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return importlib.import_module(mod_name)
