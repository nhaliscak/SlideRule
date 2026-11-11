"""Builder for the calculations that deepen the thinnest sub-disciplines (any discipline, same shape as the physics/chemistry builders)."""

from ._pc import _build


def mk(discipline, cid, name, subs, desc, variables, equations, outputs, example, ref, assume, *, extra=(), tags=(), validity=()):
    return _build(discipline, cid, name, subs, desc, variables, equations, outputs, example, ref, assume, extra, tags, validity)
