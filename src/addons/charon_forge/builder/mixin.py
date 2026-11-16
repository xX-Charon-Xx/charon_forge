"""The high res library, layered onto a builder class.
Goes in front of either our Builder or the base builder addon's (see host.py)."""

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
        """Mirror and flip show the twin's own model, so the scene matches what a save reloads.
        Parts the libraries don't cover keep the flipped copy, faces turned the right way out."""
        # the addon only copies a shared mesh; a sole user of a library's cached mesh
        # would flip that cache for every later placement
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
        """Every group but the Forge's spheres and shapes, which serialise() saves itself."""
        return [
            group_obj
            for group_obj in super(HighResBuilderMixin, self).get_all_groups()
            if not Forged.is_forged(group_obj)
        ]

    def get_all_forged(self):
        return Forged.get_all()

    # Saving ---
    def serialise(self, *args, **kwargs):
        """The base serialise plus the Forge's objects as their parts,
        with priority parts first while Auto Optimise is on."""
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
        """Reconstruct the base and offer its space station if it is in one.
        The lowest order cockpit and landing bay are marked primary."""
        before = set(bpy.data.objects)
        result = self._deserialise_base(data)
        # the ship's own cockpit and landing bay, picked in the optimiser panel
        imported = [obj for obj in bpy.data.objects if obj not in before]
        optimiser_utils.mark_primary_parts(imported)
        station_prompt.offer_station(data)
        return result

    def _deserialise_base(self, data):
        """Reconstruct the base: parts from the high res library, the rest by the base class."""
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
    """Point a just mirrored or flipped part at its twin's own model.
    Returns False, leaving it untouched, when there's no model for the twin."""
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
