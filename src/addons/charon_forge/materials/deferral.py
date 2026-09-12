"""Collapsing the whole-library passes of a bulk build into one each.

dedupe.dedupe_appended_data() and the no-argument form of
finish_nodes.ensure_finish_nodes() both walk every material node tree in the
file. That is the right cost to pay once at the end of an import, and the
wrong one to pay per part: placing a part calls all of them, so a scene wide
rebuild - a proxy quality switch, a batch replace - spends most of its time
rescanning a library that only the last pass could have changed.

Inside defer_shared_data() they record that they were wanted and return
immediately, and leaving the block runs each of them once.
"""

import contextlib

_defer_depth = 0
_defer_pending = False


@contextlib.contextmanager
def defer_shared_data():
    """Collapse the whole-library passes inside a bulk build into one each.

    Nests: only the outermost block runs the deferred passes, so a caller can
    wrap a batch without caring whether something inside it does the same.

    Nothing is deferred that a caller asked for explicitly - passing a
    materials list to ensure_finish_nodes() still does exactly that work, since
    that form is already scoped to what changed.
    """
    global _defer_depth, _defer_pending
    _defer_depth += 1
    try:
        yield
    finally:
        _defer_depth -= 1
        if _defer_depth == 0 and _defer_pending:
            _defer_pending = False
            # imported here, both of them import this module
            from . import dedupe, finish_nodes

            # dedupe first, so the surviving shared materials are the ones
            # that get the finish nodes rather than copies about to be thrown
            # away - the same order a bulk import uses.
            dedupe.dedupe_appended_data()
            finish_nodes.ensure_finish_nodes()


def should_defer():
    """Record that a deferred pass was wanted. True if it should be skipped."""
    global _defer_pending
    if not _defer_depth:
        return False
    _defer_pending = True
    return True


def note_appended_data():
    """Record that an asset was appended, for whatever tidy up comes next.

    Appending brings its own copies of the asset's textures and of the
    colourise node group with it, and both have to be collapsed onto the ones
    already in the file before the finish nodes are spliced in. Inside
    defer_shared_data() this is what schedules that single pass at the end.

    Outside one it deliberately does nothing: the callers that append without
    deferring - builder placement and the bulk importer - already run the
    passes themselves, and running them here as well would put the per asset
    cost back that deferring exists to remove.
    """
    should_defer()
