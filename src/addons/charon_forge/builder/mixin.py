"""The high res library, layered onto a builder class.

HighResBuilderMixin replaces how a builder places parts and loads bases, and
leaves everything else - scene lookups, serialising, presets, rigs - to the
builder it is mixed into. It relies only on what every builder has
(get_part_class, add_part, add_to_part_cache, get_obj_path,
deserialise_from_data), so it goes in front of either:

    class CharonBuilder(HighResBuilderMixin, Builder)       # ours, builder.py
    type(..., (HighResBuilderMixin, HostBuilder), {})       # the base builder
                                                            # addon's, host.py

The second is what makes it possible to hand our builder to the base builder
addon through its set_builder() hook - that hook only accepts subclasses of
its own Builder class.
"""

from . import asset_library, importer, placement
from ..objects.sphere import Sphere
from ..utils import optimiser_utils


class HighResBuilderMixin(object):

    # False makes the builder behave exactly like the class it is mixed into
    use_high_res = True

    # Building ---
    def add_part(self, object_id, user_data=None, build_rigs=True, high_res=None):
        """Add a part, from the high res library when it has one."""
        high_res = self.use_high_res if high_res is None else high_res
        return placement.add_part(
            self, object_id, user_data=user_data, build_rigs=build_rigs, high_res=high_res
        )

    def add_proxy_part(self, object_id, user_data=None, build_rigs=True):
        """Add a part the base class's way, from its fbx proxy."""
        return super(HighResBuilderMixin, self).add_part(
            object_id, user_data=user_data, build_rigs=build_rigs
        )

    # Mirroring ---
    def mirror_part(self, part_object):
        twin_id = placement.get_default_part_class(self).get_mirror_part_id(
            part_object["ObjectID"]
        )
        if self._swap_to_high_res_twin(part_object, twin_id):
            return part_object
        return super(HighResBuilderMixin, self).mirror_part(part_object)

    def flip_part(self, part_object):
        twin_id = placement.get_default_part_class(self).get_flip_part_id(
            part_object["ObjectID"]
        )
        if self._swap_to_high_res_twin(part_object, twin_id):
            return part_object
        return super(HighResBuilderMixin, self).flip_part(part_object)

    def _swap_to_high_res_twin(self, part_object, twin_id):
        """Point a part at its mirrored/flipped twin's library mesh.

        High res parts share one mesh per ObjectID, so scaling that mesh by -1
        the way the base class does would turn every other copy of the part
        inside out. The twin is usually its own model in the library, in which
        case pointing at it is the whole job and nothing is flipped. When it
        isn't, this returns False and the base class flips a copy instead.
        """
        if not self.use_high_res:
            return False

        twin_mesh = asset_library.load_high_res_mesh(twin_id)
        if twin_mesh is None:
            return False

        old_id = part_object["ObjectID"]
        part_object.data = twin_mesh
        part_object["ObjectID"] = twin_id
        part_object.name = twin_id
        self._forget_cached(old_id)
        self.add_to_part_cache(twin_id, part_object)
        return True

    def _forget_cached(self, object_id):
        # Both builders keep their part cache in a private self.__part_cache,
        # which Python stores as _Builder__part_cache since both classes are
        # named Builder. Without this the old id would keep pointing at the
        # renamed object.
        cache = getattr(self, "_Builder__part_cache", None)
        if isinstance(cache, dict):
            cache.pop(object_id, None)

    # Lookups ---
    def get_all_groups(self):
        """Every group but the Forge spheres, which serialise() saves with
        their own serialiser. A sphere carries a GroupID so the group tools
        work on it, and the base class would otherwise save it as a group."""
        return [
            group_obj
            for group_obj in super(HighResBuilderMixin, self).get_all_groups()
            if not Sphere.is_sphere(group_obj)
        ]

    def get_all_spheres(self):
        return Sphere.get_all_spheres()

    # Saving ---
    def serialise(self, *args, **kwargs):
        """The base class's serialise with the Forge spheres added as their
        parts, and priority parts put first while Auto Optimise is on - see
        optimiser_utils.reorder_scene_objects."""
        auto_optimise = optimiser_utils.is_auto_optimise_on()
        if auto_optimise:
            ranks = optimiser_utils.get_priority_ranks()
            optimiser_utils.reorder_scene_objects(self, ranks)

        data = super(HighResBuilderMixin, self).serialise(*args, **kwargs)
        key = "Prefab" if kwargs.get("as_prefab") else "Objects"

        # spheres go out with the groups, the way the base class treats them
        if kwargs.get("include_groups", True) and isinstance(data.get(key), list):
            for sphere_obj in self.get_all_spheres():
                data[key] += Sphere.serialise(sphere_obj)

        if auto_optimise:
            for data_key in ("Objects", "Prefab"):
                if isinstance(data.get(data_key), list):
                    optimiser_utils.sort_serialised_objects(data[data_key], ranks)
        return data

    # Loading ---
    def deserialise_from_data(self, data):
        """Given NMS data, reconstruct the base.

        The parts are built here, from the high res library. Presets, rigs and
        control points are left to the base class, which is handed the same
        data with the parts taken out.
        """
        if data is None:
            return

        if not self.use_high_res:
            return super(HighResBuilderMixin, self).deserialise_from_data(data)

        base_version = data.get("BaseVersion", 8)
        importer.import_objects(
            self, data.get("Objects", []), compensate_normal=base_version >= 5
        )

        remaining = dict(data)
        remaining["Objects"] = []
        super(HighResBuilderMixin, self).deserialise_from_data(remaining)
