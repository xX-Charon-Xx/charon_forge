"""Flat materials - one coloured material in slot 0, for the fbx proxies and
the line parts.

MaterialProvider has the same methods as the base builder addon's
MaterialProvider, so the high res routing in mixin.py can go in front of either.
Override only what you need: the other methods go through self, so replacing
validate_material() alone changes every material this makes. Keep
"transparent" in the name of ghosted materials, the ghost toggle looks for it.
"""

import bpy

from ..nms.utils import python as python_utils
from ..nms.utils import userdata
from . import colouring, palettes, paths
from .properties import PROP_READONLY_COLOUR, PROP_READONLY_MATERIAL, PROP_USER_DATA

GHOSTED_ITEMS = python_utils.load_dictionary(paths.GHOSTED_JSON)["GHOSTED"]


class MaterialProvider(object):
    """Creates and assigns flat materials."""

    def validate_material(self, colour_name, colour_value):
        """Creates or returns a material based on its name.

        Args:
            colour_name (str): The name of the material.
            colour_value (list): RGBA values representing the colour.

        Returns:
            bpy.Material: The Blender material.
        """
        colour_material = bpy.data.materials.get(colour_name, None)
        if not colour_material:
            colour_material = bpy.data.materials.new(name=colour_name)
            colour_material.diffuse_color = colour_value
        return colour_material

    def set_material(self, item, material):
        """Put a material into an item's first slot.

        Returns:
            bpy.Material: The material, or None if the item takes no materials.
        """
        if not hasattr(item.data, "materials"):
            return
        if not item.data.materials:
            item.data.materials.append(material)
        else:
            item.data.materials[0] = material
        return material

    def assign_power_material(self, item):
        """Assign light blue material to object."""
        material = self.validate_material("powerline_material", [0.0, 0.5, 1.0, 0.5])
        self.set_material(item, material)

    def assign_portal_material(self, item):
        """Assign teal material to object."""
        material = self.validate_material("portalline_material", [0.0, 1.0, 1.0, 0.5])
        self.set_material(item, material)

    def assign_pipe_material(self, item):
        """Assign grey material to object."""
        material = self.validate_material("pipeline_material", [0.3, 0.3, 0.3, 0.9])
        self.set_material(item, material)

    def assign_bytebeat_material(self, item):
        """Assign light purple material to object."""
        material = self.validate_material("bytebeat_material", [0.8, 0.0, 0.8, 0.5])
        self.set_material(item, material)

    def assign_preset_material(self, item):
        """Assign gold material to object."""
        material_name = "preset_material"
        if item.get("ObjectID", "") in GHOSTED_ITEMS:
            material_name += "_transparent"

        material = self.validate_material(material_name, [0.8, 0.300186, 0.178301, 1.0])
        self.set_material(item, material)

    def assign_default_material(self, item, index=0):
        """Assign the default grey material and UserData index.

        Returns:
            bpy_types.Material: The material that is applied.
        """
        item[PROP_USER_DATA] = str(index)
        material = self.validate_material("default_material", [0.8, 0.8, 0.8, 1.0])
        self.set_material(item, material)
        return material

    def get_colour_from_palette_data(self, colour_index, material_index):
        """The flat colour for a colour index."""
        return palettes.get_colour_from_palette_data(colour_index, material_index)

    def restore_material(self, item, user_data_value):
        """Paint an item from a packed UserData value."""
        try:
            user_data_value = int(user_data_value)
        except ValueError:
            return
        self.assign_material(
            item,
            userdata.get_colour(user_data_value),
            userdata.get_material(user_data_value),
        )

    def assign_material(self, item, colour_index=0, material_index=0):
        """Assign a colour and finish, and write them into the item's UserData.

        Returns:
            bpy_types.Material: The material that is applied.
        """
        reference_value = int(item.get(PROP_USER_DATA, 0))
        new_userdata_value = userdata.update_colour_material(
            reference_value, colour_index=colour_index, material_index=material_index
        )
        item[PROP_USER_DATA] = str(new_userdata_value)

        colour_name = "{0}_material".format(new_userdata_value)
        if item.get("ObjectID", "") in GHOSTED_ITEMS:
            colour_name += "_transparent"

        primary = self.get_colour_from_palette_data(colour_index, material_index)
        if isinstance(primary, str):
            primary = eval(primary)
        # copy so the baked palette entry isn't extended in place
        primary = list(primary)
        if len(primary) < 4:
            primary.append(1.0)

        material = self.validate_material(colour_name, primary)

        # readable names for the viewport overlay
        nice_name = palettes.get_nice_name_from_indicies(colour_index, material_index)
        if nice_name and ":" in nice_name:
            item[PROP_READONLY_MATERIAL] = nice_name.split(":")[0].strip()
            item[PROP_READONLY_COLOUR] = nice_name.split(":")[1].strip()

        self.set_material(item, material)
        return material


def optimise_materials():
    """Make flat parts with the same ObjectID and UserData share one mesh.

    Parts with an override class and curve followers are left alone, they
    manage their own meshes.
    """
    from ..nms.part_overrides import parts_override

    classes_dict = parts_override.get_override_classes()

    unique_materials = {}
    for obj in bpy.context.scene.objects:
        if "ObjectID" not in obj or obj.get("curve_parent") is not None:
            continue

        obj_id = obj.get("ObjectID")
        if obj_id in classes_dict:
            continue

        # high res parts already share one mesh per ObjectID across every
        # UserData, so there is nothing to gain here and plenty to lose.
        # Copying them is nearly free in memory while the file is open
        # (blender shares mesh arrays until they are edited) but the copies
        # are written out separately: on a 6000 part base this turned an 89 MB
        # save into 945 MB, and 1225 MB of RAM into 2157 MB on the next open,
        # worsening with every save/open cycle.
        if colouring.is_high_res(obj):
            continue

        key = (obj_id, obj.get(PROP_USER_DATA))
        if key not in unique_materials:
            # make sure the data block isn't shared with anything else
            obj.data = obj.data.copy()
            unique_materials[key] = obj.data
        else:
            obj.data = unique_materials[key]
