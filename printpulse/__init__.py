__version__ = "0.1.2"


def require_dependency(package: str, import_name: str | None = None):
    """Import a package, raising a clear error if not installed.

    Args:
        package: The pip package name (e.g. "feedparser").
        import_name: The Python import name if different from the pip name.

    Returns:
        The imported module.

    Raises:
        ImportError: With a message explaining how to install the package.
    """
    import importlib
    mod_name = import_name or package
    try:
        return importlib.import_module(mod_name)
    except ImportError:
        raise ImportError(
            f"Required package '{package}' is not installed. "
            f"Install it with: pip install {package}"
        ) from None
