"""The UI drawn inside the "Base Builder" dropdown."""

import math

import bpy

from .. import addon_preferences
from ..addon import asset_browser_presentation
from ..utils import base_builder_utils, icon_utils

# The clipboard import/export and the save editor are features of the addon
# this menu was ported from that Charon Forge doesn't have yet. The I/O
# dropdown draws their parts only once they exist, so it lights up by itself
# when they are added rather than raising from every redraw until then.
CLIPBOARD_IMPORT_OP = "object.nms_import_nms_data"
CLIPBOARD_EXPORT_OP = "object.nms_export_nms_data"
EXPORT_PINNED_BASE_OP = "object.export_pinned_base"

# The save manager - its scene.nms_save_data, the pin/import/export
# operators and the UI drawing them - is the base builder addon's. Charon
# Forge's save_editor copy only reads and writes save files for the
# Helmsman, and registers none of that.
SAVE_EDITOR_PRESENTATION = "save_editor.save_editor_presentation"


# The Charon dropdown's right column - Import / Export and the Save
# Manager - is hidden for now; True brings it back beside the assets manager.
SHOW_IMPORT_EXPORT = False

# Quick Access shows this many search results, recent or favourite parts:
# four rows of four, the rows it doesn't fill kept as blank tiles
QUICK_ACCESS_COLUMNS = 4
QUICK_ACCESS_ROWS = 4
QUICK_ACCESS_LIMIT = QUICK_ACCESS_COLUMNS * QUICK_ACCESS_ROWS
QUICK_ACCESS_ICON_SIZE = 3


def draw_empty_rows(layout, count):
    """`count` rows of blank space, each as tall as a row of asset tiles -
    a QUICK_ACCESS_ICON_SIZE icon over a line for its name (see
    asset_browser_presentation.draw_grid_element) - with no box drawn."""
    for _ in range(max(count, 0)):
        row = layout.row(align=True)
        for _ in range(QUICK_ACCESS_COLUMNS):
            tile = row.column(align=True)
            icon_space = tile.row()
            icon_space.scale_y = QUICK_ACCESS_ICON_SIZE
            icon_space.label(text="")
            tile.label(text="")


def operator_exists(idname):
    """True when an operator like "object.foo" is registered."""
    category, _, name = idname.partition(".")
    return hasattr(bpy.types, f"{category.upper()}_OT_{name}")


def get_save_editor_presentation():
    """The base builder addon's save editor presentation module, or None
    while that addon isn't loaded. Looked up in sys.modules each time, so it
    is picked up once the addon is enabled - and never imported from here."""
    return base_builder_utils.get_module(SAVE_EDITOR_PRESENTATION)


def _draw_needs_host(layout, feature):
    note = layout.column(align=True)
    note.scale_y = 0.8
    note.label(text=f"{feature} needs the", icon="INFO")
    note.label(text=f"{base_builder_utils.HOST_ADDON_NAME} addon", icon="BLANK1")


class VIEW3D_PT_nms_io_panel(bpy.types.Panel):
    """ Save Files Browser """

    bl_idname = "VIEW3D_PT_nms_io_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_label = "I/O"
    # Popovers size themselves from this rather than from their content.
    bl_ui_units_x = 14


    def draw(self, context):
        draw_import_export(self.layout, context)
        draw_save_manager(self.layout, context)


def get_pinned_base(context):
    """(save data, base tool props) while a base is pinned, else None."""
    save_data = getattr(context.scene, "nms_save_data", None)
    base_props = getattr(context.scene, "nms_base_tool", None)
    if save_data is None or base_props is None or not save_data.pinned_base_check:
        return None
    return save_data, base_props


def draw_save_manager(layout, context):
    """Picking a save, and a base or corvette in it to import, export or pin -
    the bottom of the Charon dropdown. The pinned base itself is with the
    import/export."""
    save_editor_presentation = get_save_editor_presentation()
    save_data = getattr(context.scene, "nms_save_data", None)
    if save_editor_presentation is None:
        _draw_needs_host(layout, "The Save Manager")
        return
    # as its own panel: nothing to draw from until the addon's save editor
    # and preferences are registered
    if save_data is None or base_builder_utils.get_host_save_folder_path() is None:
        layout.label(text="Save Manager unavailable", icon="ERROR")
        return
    save_editor_presentation.draw_base_picker(layout.column(), save_data)


def draw_import_export(layout, context):
    """The clipboard, and the pinned base's import/export - the I/O panel,
    and the right side of the Charon dropdown."""
    nms_main = getattr(context.scene, "nms_main", None)
    drew_anything = False

    if operator_exists(CLIPBOARD_IMPORT_OP) and operator_exists(CLIPBOARD_EXPORT_OP):
        clipboard_box = layout.column(align=True)
        clipboard_box.label(text="Clipboard")
        clipboard_column = clipboard_box.row(align=True)
        clipboard_column.operator(CLIPBOARD_IMPORT_OP, icon="PASTEDOWN")
        clipboard_export_column = clipboard_column.column(align=True)
        clipboard_export_column.operator(CLIPBOARD_EXPORT_OP, icon="COPYDOWN")
        if nms_main is not None:
            clipboard_export_column.prop(nms_main, "check_export_objects_only", text="Objects Only")
        layout.separator()
        drew_anything = True

    # the pinned base: pulled from or written back to its save in one click
    save_editor_presentation = get_save_editor_presentation()
    pinned = get_pinned_base(context)
    if save_editor_presentation is not None and pinned is not None:
        pinned_column = layout.column()
        pinned_column.label(text="Pinned Base")
        save_editor_presentation.draw_pinned_base(pinned_column, *pinned)
        drew_anything = True

    if not drew_anything:
        if base_builder_utils.is_available():
            layout.label(text="Import/export isn't available yet", icon="INFO")
        else:
            column = layout.column(align=True)
            column.label(text="Clipboard import/export needs the", icon="INFO")
            column.label(text=f"{base_builder_utils.HOST_ADDON_NAME} addon", icon="BLANK1")


class VIEW3D_PT_nms_base_builder(bpy.types.Panel):
    """ Quick options related to NMS Base and Corvette Builder"""

    bl_idname = "VIEW3D_PT_nms_base_builder"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_label = "Base Builder"
    # Popovers size themselves from this rather than from their content -
    # the assets manager's 18 units, beside the import/export's 14.
    bl_ui_units_x = 33 if SHOW_IMPORT_EXPORT else 18

    def draw(self, context):
        """The dropdown: the assets manager on the left, and on the right
        import/export with the save manager under it, each its own box."""
        if not SHOW_IMPORT_EXPORT:
            assets = self.layout.column(align = True)
            assets.label(text="Assets Manager", icon="ASSET_MANAGER")
            assets.separator(factor=0.5)
            self.draw_assets_manager(assets, context)
            return

        menu_row = self.layout.row(align = True)
        split = menu_row.split(factor=0.56)

        assets = split.column(align = True)
        assets.label(text="Assets Manager", icon="ASSET_MANAGER")
        assets.separator(factor=0.5)
        self.draw_assets_manager(assets, context)

        right = split.row(align = True)
        right.separator(factor = 4)
        right_column = right.column()
        io = right_column.column(align = True)
        io.label(text="Import / Export", icon="FILE_TICK")
        io.separator(factor=0.5)
        draw_import_export(io, context)

        right_column.separator()
        save_manager = right_column.box().column(align=True)
        save_manager.label(text="Save Manager", icon="FILE_FOLDER")
        save_manager.separator(factor=0.5)
        draw_save_manager(save_manager, context)

    def draw_assets_manager(self, layout, context):
        """Proxy quality, the asset browser, quick access and search."""

        asset_browser = context.scene.nms_asset_browser
        enum_assets_quick_access_view_mode = context.scene.enum_assets_quick_access_view_mode
        pcoll = icon_utils.get_asset_icons_pcoll()
        
        
        # Drawn as two operators rather than as the enum itself: the switch
        # has to run as an operator to have its scene edits stick and be
        # undoable, so the enum only records which one was last used and
        # `depress` makes the pair read as an expanded enum.
        quality = context.scene.enum_proxy_quality
        proxy_box = layout.column(align=True)
        proxy_box.label(text="Proxy Quality")
        proxy_row = proxy_box.row(align=True)
        proxy_row.scale_y = 1.2
        proxy_row.operator(
            "object.nms_switch_proxies_to_low", text="Simple Proxies",
            icon="MESH_CUBE", depress=quality == "low",
        )
        proxy_row.operator(
            "object.nms_switch_proxies_to_high", text="High-res Proxies",
            icon="MESH_MONKEY", depress=quality == "high",
        )
        proxy_row.separator()
        proxy_row.operator("object.nms_fix_broken_textures", text="Fix Proxies", icon="FILE_REFRESH")

        # the low res models are the base builder addon's
        from .base_builder_menu_operators import simple_proxies_available
        if not simple_proxies_available():
            note = proxy_box.column(align=True)
            note.scale_y = 0.8
            note.label(text="Simple Proxies need the", icon="INFO")
            note.label(text=f"{base_builder_utils.HOST_ADDON_NAME} addon", icon="BLANK1")

        # Drawn straight off the preferences rather than mirrored onto the
        # scene: whether opening a file re-switches it is a per-user choice
        # that has to outlive the file it was toggled in.
        prefs = addon_preferences.get_addon_preferences()
        if prefs is not None:
            proxy_box.prop(prefs, "auto_switch_on_open")
    
        
        layout.separator()
        asset_browser_box = layout.column(align=True)
        asset_browser_box.label(text="Asset Browser")
        ab_row = asset_browser_box.row(align = True)
        ab_row.scale_y = 1.4
        ab_row.operator(
            "object.nms_launch_asset_browser_window", text="Launch Asset Browser", icon="ASSET_MANAGER"
        )
        
        recent_data = asset_browser.get_recent_objects_data()
        fav_data = asset_browser.get_favourite_objects_data()

        # an icon grid of asset_data ({label: object ids}), or "No Items" -
        # always QUICK_ACCESS_ROWS tall, so the dropdown keeps its size
        # whatever is showing
        def draw_assets(container, asset_data):
            shown = 0
            if asset_data:
                row = container.row(align = True)
                for subcategories, object_ids in asset_data.items():
                    asset_browser_presentation.draw_sub_category(
                        pcoll = pcoll,
                        container = row,
                        label = subcategories,
                        elements_list = object_ids,
                        number_of_columns = QUICK_ACCESS_COLUMNS,
                        icon_size = QUICK_ACCESS_ICON_SIZE,
                        grid_type = "Other",
                        show_title = False
                    )
                    shown += len(object_ids)
            else:
                container.label(text="No Items")
            draw_empty_rows(container, QUICK_ACCESS_ROWS - math.ceil(shown / QUICK_ACCESS_COLUMNS))

        # The search box and the Favourites/Recent switch share a row, and
        # the grid under them shows whichever is in use - the search's
        # results while there is anything typed, else the tab picked.
        layout.separator()
        quick_access_column = layout.column(align = True)
        quick_access_column.label(text = "Quick Access")
        searching = bool(asset_browser.quick_search_query.strip())
        quick_access_row = quick_access_column.row(align = True)
        search_field = quick_access_row.row(align = True)
        search_field.scale_x = 1.4
        search_field.prop(asset_browser, "quick_search_query", text="", icon='VIEWZOOM')
        quick_access_row.separator()
        # nothing to switch while the search's results are what's showing
        view_mode_row = quick_access_row.row(align = True)
        view_mode_row.active = not searching
        view_mode_row.prop(context.scene, "enum_assets_quick_access_view_mode", expand = True)
        quick_access_column.separator()

        if searching:
            results, total = asset_browser.get_quick_search_results(limit=QUICK_ACCESS_LIMIT)
            if results:
                draw_assets(quick_access_column, {"Search Results": results})
                if total > len(results):
                    note = quick_access_column.row()
                    note.scale_y = 0.8
                    note.label(
                        text=f"{len(results)} of {total} - type more, or use the Asset Browser",
                        icon="INFO",
                    )
            else:
                quick_access_column.label(text="Nothing matches", icon="INFO")
                draw_empty_rows(quick_access_column, QUICK_ACCESS_ROWS)
        elif enum_assets_quick_access_view_mode == "preset":
            # read in when the Asset Browser first opens - until then, here
            preset_data = asset_browser.get_preset_data()
            if not preset_data:
                preset_data = type(asset_browser).presets_data = asset_browser.get_presets_data()
            draw_assets(quick_access_column,
                        {"Presets": dict(list(preset_data.items())[:QUICK_ACCESS_LIMIT])} if preset_data else None)
        elif enum_assets_quick_access_view_mode == "recent":
            draw_assets(quick_access_column,
                        {"Recent Objects": dict(list(recent_data.items())[:QUICK_ACCESS_LIMIT])} if recent_data else None)
        else:
            draw_assets(quick_access_column,
                        {"Favourite Objects": dict(list(fav_data.items())[:QUICK_ACCESS_LIMIT])} if fav_data else None)



    
    
    