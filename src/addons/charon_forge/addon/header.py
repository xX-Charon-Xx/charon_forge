import bpy
from bpy.props import BoolProperty, IntProperty

# State for the hero panel, stored on the scene as scene.charon_header.
#
# The theme picker used to live here too, but blender's interface theme is an
# application setting rather than part of a .blend file - a Scene property
# forgets it every restart. It now lives on CharonAddonPreferences instead,
# see addon_preferences.py.
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
)
