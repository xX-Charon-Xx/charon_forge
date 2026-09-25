"""Spheres made of copies of one part.

How the copies are spread over the sphere is its topology - rings of
latitude, meridians, a geodesic, a cube grid or a spiral; see
utils/sphere_topology.py. Everything a sphere shares with the other forged
objects - the object, its points and modifier, exporting, splitting - is in
objects/forged.py.
"""

import math

from ..utils import sphere_topology as topology
from .forged import Forged, LayoutRefused


class Sphere(Forged):

    FORM = "SPHERE"
    LABEL = "Sphere"

    # the topologies whose counts are rings and copies around, and so are
    # rescaled when the arc they cover changes
    ARC_TOPOLOGIES = (topology.RINGS, topology.MERIDIANS)

    @classmethod
    def initialise(cls, settings):
        # two dozen copies around the equator to begin with - big enough to
        # read as a sphere straight away
        settings.radius = max(24 * settings.pitch_around / topology.FULL_TURN, 0.1)
        settings.counts_from_radius = True

    # Counts ---
    @staticmethod
    def _latitudes(settings):
        return tuple(sorted((settings.bottom, settings.top)))

    @staticmethod
    def _span(settings):
        bottom, top = Sphere._latitudes(settings)
        return top - bottom

    @staticmethod
    def counts(settings):
        """(rings, segments) - the two counts, in whatever the topology uses
        them for - worked out from the radius, or as typed in."""
        if not settings.counts_from_radius:
            return settings.rings, settings.segments

        # counted at its widest, so stretching it never opens gaps - it
        # crowds the copies where it is narrower instead
        radius = settings.radius * max(settings.sphere_scale)
        kind = settings.topology
        pitch_around, pitch_up = settings.pitch_around, settings.pitch_up
        rings, segments = settings.rings, settings.segments

        if kind in Sphere.ARC_TOPOLOGIES:
            steps = round(radius * Sphere._span(settings) / pitch_up)
            rings = steps + 1 if steps > 0 else 1
            segments = max(1, round(radius * settings.sweep / pitch_around))
        elif kind == topology.GEODESIC:
            # neighbouring points one part apart
            pitch = (pitch_around + pitch_up) / 2
            rings = max(1, round(topology.ICOSAHEDRON_EDGE * radius / pitch))
        elif kind == topology.CUBE:
            # each face spans a quarter turn of the sphere
            rings = max(1, round(math.pi / 2 * radius / pitch_around))
        elif kind == topology.SPIRAL:
            # as many as the whole sphere's area holds
            segments = max(1, round(4 * math.pi * radius * radius / (pitch_around * pitch_up)))
        return rings, segments

    @staticmethod
    def _whole_sphere_count(kind, rings, segments):
        """Roughly how many points a topology makes before anything outside
        top, bottom and sweep is dropped."""
        if kind == topology.GEODESIC:
            return 10 * rings * rings + 2
        if kind == topology.CUBE:
            return 6 * rings * rings
        if kind == topology.SPIRAL:
            return segments
        return rings * segments

    @staticmethod
    def record_density(settings):
        """Remember how closely typed-in counts are spaced - rings per radian
        of latitude, copies per radian around - for rescale_counts."""
        span = Sphere._span(settings)
        settings.ring_density = (settings.rings - 1) / span if span > 1e-6 else 0.0
        settings.around_density = settings.segments / settings.sweep

    @staticmethod
    def rescale_counts(settings):
        """Work typed-in counts out again for the arc they now cover, at the
        spacing they were typed in at, so shrinking the arc drops copies
        rather than squeezing them together. Always from the recorded
        spacing, never from the last counts, so dragging a slider doesn't
        drift or stick.

        Only rings and meridians: the other topologies spread their points
        over the whole sphere and just drop those out of range, so their
        spacing already holds."""
        if settings.topology not in Sphere.ARC_TOPOLOGIES:
            return
        with Forged.suspended():
            if settings.ring_density > 0.0:
                settings.rings = max(1, round(settings.ring_density * Sphere._span(settings)) + 1)
            if settings.around_density > 0.0:
                settings.segments = max(1, round(settings.around_density * settings.sweep))

    # Layout ---
    @classmethod
    def compute(cls, settings):
        rings, segments = Sphere.counts(settings)
        if Sphere._whole_sphere_count(settings.topology, rings, segments) > 20 * Forged.MAX_PARTS:
            raise LayoutRefused("Too many parts, the most is %d" % Forged.MAX_PARTS)

        bottom, top = Sphere._latitudes(settings)
        sweep, kind = settings.sweep, settings.topology
        if kind == topology.MERIDIANS:
            frames = topology.meridians(bottom, top, sweep, rings, segments)
        elif kind == topology.GEODESIC:
            frames = topology.geodesic(bottom, top, sweep, rings)
        elif kind == topology.CUBE:
            frames = topology.cube(bottom, top, sweep, rings)
        elif kind == topology.SPIRAL:
            frames = topology.spiral(bottom, top, sweep, segments)
        else:
            frames = topology.rings(
                bottom, top, sweep, rings, segments, settings.pole_density, settings.stagger
            )
        turn, centre = Forged.turn_and_centre(settings)
        positions, rotations = topology.place(
            *frames, settings.radius, turn, centre, Forged.copy_scale(settings),
            axes=settings.sphere_scale,
        )
        accepted = {"rings": rings, "segments": segments} if settings.counts_from_radius else {}
        return positions, rotations, accepted
