"""Runs the whole-library passes (dedupe, prepare_materials) once per bulk build
instead of once per part."""

import contextlib

_defer_depth = 0
_defer_pending = False


@contextlib.contextmanager
def defer_shared_data():
    """Defer the whole-library passes to the end of the outermost block.
    Calls given an explicit materials list still run right away."""
    global _defer_depth, _defer_pending
    _defer_depth += 1
    try:
        yield
    finally:
        _defer_depth -= 1
        if _defer_depth == 0 and _defer_pending:
            _defer_pending = False
            # imported here, both of them import this module
            from . import colourise, dedupe, emission, finish_nodes, samplers

            # dedupe first so the surviving shared materials get prepared,
            # same order as a bulk import
            dedupe.dedupe_appended_data()
            finish_nodes.strip_legacy_finish_nodes()
            samplers.ensure_sampler_budget()
            colourise.ensure_colourise()
            emission.ensure_emission()


def should_defer():
    """Record that a deferred pass was wanted. True if it should be skipped."""
    global _defer_pending
    if not _defer_depth:
        return False
    _defer_pending = True
    return True


def note_appended_data():
    """Schedule the post-append tidy up inside defer_shared_data().
    Does nothing outside one: those callers run the passes themselves."""
    should_defer()
