import bpy
from bpy.props import BoolProperty, IntProperty, PointerProperty

from . import header_operators, header_presentation

# State for the hero panel, stored on the scene as scene.charon_header.
# The theme picker is in addon_preferences.py, as a scene property forgets it on restart.
class Header(bpy.types.PropertyGroup):

    is_workspace_cleaned: BoolProperty(
        name="Workspace Cleaned",
        description="Whether the Blender workspace is currently simplified",
        default=False,
    )

    # dummy value, counts how many times the forge button was pressed
    forge_count: IntProperty(
        name="Forge Count",
        default=0,
        min=0,
    )

    def toggle_workspace(self):
        self.is_workspace_cleaned = not self.is_workspace_cleaned
        return self.is_workspace_cleaned

    def forge(self):
        self.forge_count += 1
        return self.forge_count


classes = (
    Header,
) + header_operators.classes + header_presentation.classes


def register():
    for _class in classes:
        bpy.utils.register_class(_class)
    bpy.types.Scene.charon_header = PointerProperty(type=Header)


def unregister():
    del bpy.types.Scene.charon_header
    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)
