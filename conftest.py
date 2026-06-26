"""Pytest session setup — silence ONE third-party, import-time warning.

    LangChainPendingDeprecationWarning: The default value of `allowed_objects`
    will change in a future version ...

This is emitted from `langgraph/cache/base/__init__.py` the moment langgraph is
imported. It is NOT caused by any deprecated API in our own code — verified by
turning DeprecationWarnings into errors across our full import → compile → invoke
path with no error raised.

Why the standard levers don't work: langchain_core force-surfaces its own
deprecation warnings (it re-arms a filter for its category during import), so a
`filterwarnings`/`simplefilter('ignore')`/`PYTHONWARNINGS=ignore` set beforehand
is overridden. We therefore intercept at the DISPLAY layer and drop only this one
specific message, leaving every other warning (including any real deprecation in
our code) fully visible.

We pre-import the offending module here, once, under the drop, before collection.
Python caches modules, so later langgraph imports during the run stay silent.
Remove this shim once langgraph is upgraded past the pending deprecation.
"""

import warnings

with warnings.catch_warnings():
    _orig_showwarning = warnings.showwarning

    def _drop_known_thirdparty_warning(message, category, filename, lineno, file=None, line=None):
        if "allowed_objects" in str(message) and "LangChain" in getattr(category, "__name__", ""):
            return  # the one known, unavoidable third-party import-time warning
        return _orig_showwarning(message, category, filename, lineno, file, line)

    warnings.showwarning = _drop_known_thirdparty_warning
    warnings.simplefilter("always")  # force emission now so the module is cached quietly
    try:  # pragma: no cover - environment guard, not a behavior under test
        import langgraph.cache.base  # noqa: F401  fires (and drops) the warning, caches module
    except Exception:
        # Fail open: worst case the cosmetic warning reappears, never a broken run.
        pass
# catch_warnings restores warnings.showwarning and the filter state on exit.
