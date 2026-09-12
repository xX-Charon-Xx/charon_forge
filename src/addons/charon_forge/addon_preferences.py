import bpy
from bpy.props import EnumProperty, IntProperty

from .utils import themes_util

ADDON_ID = __package__

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


class CharonAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    # Stored here rather than on the scene: blender's interface theme is an
    # application setting, not part of a .blend file, and addon preferences
    # are what survives a restart - see __init__.py's register(), which
    # re-applies this every time the addon loads so the actual colours always
    # agree with what the dropdown says is selected.
    theme: EnumProperty(
        name="Theme",
        description="Choose one of Charon Forge's bundled themes",
        items=get_theme_enum_items,
        update=on_theme_update,
    )

    # Applied to every scene whenever a blend file is opened (or a new one is
    # created) - see menu/base_builder_menu.py's load_post handler. Also what
    # scene.enum_proxy_quality starts out as for a scene that has never been
    # touched by that handler yet.
    default_proxy_quality: EnumProperty(
        name="Default Proxy Quality",
        description="Mesh source to switch every part and group to whenever a blend file is opened",
        items=[
            ("low", "Simple Proxies", "Use the old fbx proxies from the models folder", "MESH_CUBE", 0),
            ("high", "High-res Proxies", "Use the high res library, where a part has one", "MESH_MONKEY", 1),
        ],
        default="high",
    )

    # Icon size / column count per asset browser view mode. Read through
    # nms/utils/asset_browser_utils.get_grid_size_properties(), ported from
    # the reference addon's addon_preferences.py.
    asset_browser_icon_size: IntProperty(
        name="Size", description="Icon size", default=3, min=1, max=10,
        options={'TEXTEDIT_UPDATE'},
    )
    asset_browser_number_of_columns: IntProperty(
        name="Columns", description="Number of elements to display in each row",
        default=3, min=1, max=10, options={'TEXTEDIT_UPDATE'},
    )
    asset_browser_icon_size_list: IntProperty(
        name="Size", description="Icon size", default=2, min=1, max=10,
        options={'TEXTEDIT_UPDATE'},
    )
    asset_browser_number_of_columns_list: IntProperty(
        name="Columns", description="Number of elements to display in each row",
        default=3, min=1, max=16, options={'TEXTEDIT_UPDATE'},
    )
    asset_browser_icon_size_other: IntProperty(
        name="Size", description="Icon size", default=4, min=1, max=10,
        options={'TEXTEDIT_UPDATE'},
    )
    asset_browser_number_of_columns_other: IntProperty(
        name="Columns", description="Number of elements to display in each row",
        default=10, min=4, max=15, options={'TEXTEDIT_UPDATE'},
    )

    def draw(self, context):
        layout = self.layout
        layout.row().prop(self, "theme", text="Theme")
        layout.row().prop(self, "default_proxy_quality", expand=True)


def get_addon_preferences():
    addon = bpy.context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None
