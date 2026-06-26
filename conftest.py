"""Pytest session setup — silence known third-party, import-time warnings.

Two warnings are emitted at IMPORT time by dependencies, neither caused by any
deprecated API in our own code:

1. `LangChainPendingDeprecationWarning: The default value of allowed_objects ...`
   from `langgraph/cache/base/__init__.py` when langgraph is imported.
2. `StarletteDeprecationWarning: Using httpx with starlette.testclient is
   deprecated ...` from `fastapi.testclient` (test client only, not src/api.py).

We verified our own code is clean by turning DeprecationWarnings into errors
across the full import → compile → invoke path with no error raised.

Why the standard levers don't fully work: langchain_core force-surfaces its own
deprecation warnings (it re-arms a filter for its category during import), so a
`filterwarnings`/`simplefilter('ignore')`/`PYTHONWARNINGS=ignore` set beforehand
is overridden. We therefore intercept at the DISPLAY layer and drop only these
specific messages, leaving every other warning (including any real deprecation in
our code) fully visible.

We pre-import the offending modules here, once, under the drop, before
collection. Python caches modules, so later imports during the run stay silent.
Remove an entry once its dependency is upgraded past the deprecation.
"""

import warnings

with warnings.catch_warnings():
    _orig_showwarning = warnings.showwarning

    def _drop_known_thirdparty_warning(message, category, filename, lineno, file=None, line=None):
        text = str(message)
        name = getattr(category, "__name__", "")
        if "allowed_objects" in text and "LangChain" in name:
            return  # langgraph -> langchain_core pending deprecation
        if "starlette.testclient" in text:
            return  # starlette TestClient httpx deprecation (test tooling only)
        return _orig_showwarning(message, category, filename, lineno, file, line)

    warnings.showwarning = _drop_known_thirdparty_warning
    warnings.simplefilter("always")  # force emission now so the modules cache quietly
    for _module in ("langgraph.cache.base", "fastapi.testclient"):
        try:  # pragma: no cover - environment guard, not a behavior under test
            __import__(_module)  # fires (and drops) the warning, caches module
        except Exception:
            # Fail open: worst case a cosmetic warning reappears, never a broken run.
            pass
# catch_warnings restores warnings.showwarning and the filter state on exit.
