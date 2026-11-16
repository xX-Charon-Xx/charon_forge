"""Flat materials - one coloured material in slot 0, for the fbx proxies and
the line parts. Ghosted materials keep "transparent" in their name."""

import bpy

from ..utils import loading_overlay
from ..utils.base_builder_utils import overrides, python_utils, userdata
from . import colouring, palettes, paths
from .properties import PROP_READONLY_COLOUR, PROP_READONLY_MATERIAL, PROP_USER_DATA

# loaded lazily: the base builder addon may not be loaded yet at import time
_ghosted_items = None


def _get_ghosted_items():
    global _ghosted_items
    if _ghosted_items is None:
        _ghosted_items = python_utils.load_dictionary(paths.GHOSTED_JSON)["GHOSTED"]
    return _ghosted_items


def __getattr__(name):
    # Keeps `from .flat import GHOSTED_ITEMS` (materials/__init__.py) working
    # without loading it at import time - see _get_ghosted_items above.
    if name == "GHOSTED_ITEMS":
        return _get_ghosted_items()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class MaterialProvider(object):
    """Creates and assigns flat materials."""

    def validate_material(self, colour_name, colour_value):
        """Get the material by name, or make it with this RGBA colour."""
        colour_material = bpy.data.materials.get(colour_name, None)
        if not colour_material:
            colour_material = bpy.data.materials.new(name=colour_name)
            colour_material.diffuse_color = colour_value
        return colour_material

    def set_material(self, item, material):
        """Put a material into an item's first slot; None if it takes no materials."""
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
        if item.get("ObjectID", "") in _get_ghosted_items():
            material_name += "_transparent"

        material = self.validate_material(material_name, [0.8, 0.300186, 0.178301, 1.0])
        self.set_material(item, material)

    def assign_default_material(self, item, index=0):
        """Assign the default grey material and UserData index."""
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
        """Assign a colour and finish, and write them into the item's UserData."""
        reference_value = int(item.get(PROP_USER_DATA, 0))
        new_userdata_value = userdata.update_colour_material(
            reference_value, colour_index=colour_index, material_index=material_index
        )
        item[PROP_USER_DATA] = str(new_userdata_value)

        colour_name = "{0}_material".format(new_userdata_value)
        if item.get("ObjectID", "") in _get_ghosted_items():
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
    Override-class parts and curve followers are left alone."""
    unique_materials = {}
    for obj in bpy.context.scene.objects:
        if "ObjectID" not in obj or obj.get("curve_parent") is not None:
            continue
        loading_overlay.step("Sharing meshes")

        obj_id = obj.get("ObjectID")
        try:
            has_override = overrides.get_override_class(obj_id) is not None
        except AttributeError:
            has_override = False
        if has_override:
            continue

        # high res parts already share one mesh; copying them bloats the saved
        # file (89 MB to 945 MB on a 6000 part base)
        if colouring.is_high_res(obj):
            continue

        key = (obj_id, obj.get(PROP_USER_DATA))
        if key not in unique_materials:
            # make sure the data block isn't shared with anything else
            obj.data = obj.data.copy()
            unique_materials[key] = obj.data
        else:
            obj.data = unique_materials[key]
