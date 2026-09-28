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

import bpy

from . import asset_library, importer, placement, proxy_library, station_prompt
from .. import materials
from ..objects.part import Part
from ..objects.shapes import circle, cuboid, polygon, qr, rectangle, shape, sphere, text  # noqa: F401 - registers the forged kinds
from ..objects.shapes.forged import Forged
from ..utils import optimiser_utils

# what the libraries mark the meshes they cache and hand out again with
_CACHE_TAGS = (
    materials.MESH_TAG,
    proxy_library.PROXY_MESH_TAG,
    proxy_library.PROXY_PLACEMENT_TAG,
)


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
    def _swap_to_twin(self, part_object, new_object_id, flip_axis):
        """The base builder addon's mirror and flip, showing the twin's own
        model rather than a flipped copy of this one.

        The addon's mirror_part / flip_part scale the part's mesh by -1 on one
        axis and give it the twin's id. But a save only carries the id and the
        transform, so the next import places the twin's own model - which for
        most pairs is not this mesh flipped (B_STR_T_NWTB is B_STR_T_NETB
        flipped; B_STR_A_S is B_STR_A_N flipped AND turned about up; a _Y_
        flip is a half turn, not a mirror). What the scene showed was then not
        what came back. Showing the twin's model makes the two the same; the
        mirror tool's transform is corrected to suit it, see mirror_fit.

        A part the libraries don't cover keeps the addon's flipped copy, with
        its faces turned back the right way out - Mesh.transform doesn't
        reverse the winding for a negative scale, so a material with backface
        culling showed the part from inside (B_STR_AA_N, B_DECO_Q_0).
        """
        # The addon only copies a mesh that has other users. A part that is
        # the sole user of a library's cached mesh would have that cache
        # flipped in place, and every later placement of the id with it.
        mesh = part_object.data
        if mesh.users == 1 and any(tag in mesh for tag in _CACHE_TAGS):
            part_object.data = mesh.copy()

        result = super(HighResBuilderMixin, self)._swap_to_twin(
            part_object, new_object_id, flip_axis
        )

        flipped = part_object.data
        if _show_twin_model(part_object, mesh, new_object_id):
            if flipped.users == 0:
                bpy.data.meshes.remove(flipped)
        else:
            flipped.flip_normals()
        return result

    # Lookups ---
    def get_all_groups(self):
        """Every group but the Forge's spheres and shapes, which serialise()
        saves with their own serialiser. They carry a GroupID so the group
        tools work on them, and the base class would otherwise save them as
        groups."""
        return [
            group_obj
            for group_obj in super(HighResBuilderMixin, self).get_all_groups()
            if not Forged.is_forged(group_obj)
        ]

    def get_all_forged(self):
        return Forged.get_all()

    # Saving ---
    def serialise(self, *args, **kwargs):
        """The base class's serialise with the Forge's objects added as their
        parts, and priority parts put first while Auto Optimise is on - see
        optimiser_utils.reorder_scene_objects."""
        auto_optimise = optimiser_utils.is_auto_optimise_on()
        if auto_optimise:
            ranks = optimiser_utils.get_priority_ranks()
            optimiser_utils.reorder_scene_objects(self, ranks)

        data = super(HighResBuilderMixin, self).serialise(*args, **kwargs)
        key = "Prefab" if kwargs.get("as_prefab") else "Objects"

        # forged objects go out with the groups, the way the base class treats them
        if kwargs.get("include_groups", True) and isinstance(data.get(key), list):
            for forged_obj in self.get_all_forged():
                data[key] += Forged.serialise(forged_obj)

        if auto_optimise:
            for data_key in ("Objects", "Prefab"):
                if isinstance(data.get(data_key), list):
                    optimiser_utils.sort_serialised_objects(data[data_key], ranks)
        return data

    # Loading ---
    def deserialise_from_data(self, data):
        """Given NMS data, reconstruct the base - and if it is a base inside a
        space station, offer to build that station (see station_prompt). The
        lowest order cockpit and landing bay it brings are marked primary."""
        before = set(bpy.data.objects)
        result = self._deserialise_base(data)
        # the ship's own cockpit and landing bay, picked in the optimiser panel
        imported = [obj for obj in bpy.data.objects if obj not in before]
        optimiser_utils.mark_primary_parts(imported)
        station_prompt.offer_station(data)
        return result

    def _deserialise_base(self, data):
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


def _show_twin_model(part_object, source_mesh, twin_id):
    """Point a part that was just mirrored or flipped at its twin's own model,
    out of the library its mesh came from.

    Returns:
        bool: False when that library has no model for the twin (or the mesh
            is from neither library), in which case the object is untouched.
    """
    # an alternate form shows another id's model, see placement.add_part
    if "nms_form_model" in part_object:
        return False

    user_data = part_object.get(Part.PROP_USER_DATA, Part.DEFAULT_USER_DATA)

    if materials.MESH_TAG in source_mesh:
        twin_mesh = asset_library.load_high_res_mesh(twin_id)
        if twin_mesh is None:
            return False
        part_object.data = twin_mesh
        # colour resolves by id, and the twin's default palette may differ
        materials.recolour_from_user_data([part_object], user_data)
        materials.dedupe_appended_data()
        materials.prepare_materials(twin_mesh.materials)
        return True

    if (proxy_library.PROXY_MESH_TAG in source_mesh
            or proxy_library.PROXY_PLACEMENT_TAG in source_mesh):
        return proxy_library.apply_proxy_mesh(part_object, twin_id, user_data)

    return False
