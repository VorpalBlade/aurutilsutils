def get_version():
    """Get the version of aurutilsutils"""
    try:
        from .. import _version

        return _version.__version__
    except ImportError:
        return "unknown version"
