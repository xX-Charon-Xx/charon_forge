import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty

from ..utils import themes_util

# kept alive at module level: EnumProperty items callbacks must return a
# list backed by something other than a local variable, or blender can
# crash once the strings it built are garbage collected
_theme_enum_items = []


def get_theme_enum_items(self, context):
    global _theme_enum_items
    # blender's own default theme goes on top, ahead of the ones in themes.json
    _theme_enum_items = [
        (themes_util.DEFAULT_THEME_ID, "Blender Default", "Blender's built-in default dark theme"),
    ]
    _theme_enum_items += [
        (name, name.replace("_", " ").title(), themes_util.get_theme_path(name) or "")
        for name in themes_util.list_themes()
    ]
    return _theme_enum_items


def on_theme_update(self, context):
    themes_util.apply_named_theme(self.theme)


# State for the hero panel, stored on the scene as scene.charon_header
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

    theme: EnumProperty(
        name="Theme",
        description="Choose one of Charon Forge's bundled themes",
        items=get_theme_enum_items,
        update=on_theme_update,
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
