import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

from .utils import base_builder_utils, themes_util

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

    # Whether that handler runs at all. Off leaves an opened file at whatever
    # quality it was saved at, for working on a base built at one quality
    # without it being switched out from under you on every open.
    auto_switch_on_open: BoolProperty(
        name="Auto Switch on Open",
        description=(
            "Switch every part and group to the default proxy quality "
            "whenever a blend file is opened"
        ),
        default=True,
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

    # Whether the priority list panel shows each group's icon strip. A
    # display preference rather than something about the file being worked
    # on, so it lives here (per user, across restarts) rather than on
    # scene.charon_optimiser - see optimiser_presentation.py.
    show_preview: BoolProperty(
        name="Show Preview",
        description="Show a preview of the first few parts in each priority group",
        default=True,
    )

    # Dummy for now - nothing acts on it yet.
    auto_optimise: BoolProperty(
        name="Auto Optimise",
        description="Optimise automatically as parts are placed",
        default=False,
    )

    # Left blank by default rather than filled in with the host's folder at
    # class definition time - base_builder_utils looks the host addon up
    # among already loaded modules (see its module docstring), which is not
    # guaranteed to be the case yet while blender is still importing addons.
    # get_save_folder_path() below falls back to the host's own folder for
    # as long as this stays blank.
    save_folder_path: StringProperty(
        name="Save Directory",
        description="Folder where NMS save files are stored",
        subtype='DIR_PATH',
        default="",
    )

    def draw(self, context):
        layout = self.layout
        layout.row().prop(self, "theme", text="Theme")
        layout.row().prop(self, "default_proxy_quality", expand=True)
        layout.row().prop(self, "auto_switch_on_open")
        layout.row().prop(self, "show_preview")
        layout.row().prop(self, "auto_optimise")
        layout.row().prop(self, "save_folder_path")


def get_addon_preferences():
    addon = bpy.context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None


def get_save_folder_path():
    """The NMS save folder to use, or None.

    The user's own choice if they have set one, else whatever the host
    addon's save manager is pointed at, else the game's usual folder for
    this OS (save_editor_utils.get_default_save_folder) when it exists.
    """
    prefs = get_addon_preferences()
    if prefs is not None and prefs.save_folder_path:
        return prefs.save_folder_path

    host_path = base_builder_utils.get_host_save_folder_path()
    if host_path:
        return host_path

    import os
    from .save_editor import save_editor_utils

    default_path = str(save_editor_utils.get_default_save_folder())
    return default_path if os.path.isdir(default_path) else None
