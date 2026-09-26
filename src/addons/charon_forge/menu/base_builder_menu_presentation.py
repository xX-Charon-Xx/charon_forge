"""The UI drawn inside the "Base Builder" dropdown."""

import importlib

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

# where a ported save editor's presentation module would live
SAVE_EDITOR_PRESENTATION = "..save_editor.save_editor_presentation"


def operator_exists(idname):
    """True when an operator like "object.foo" is registered."""
    category, _, name = idname.partition(".")
    return hasattr(bpy.types, f"{category.upper()}_OT_{name}")


_NOT_LOOKED_UP = object()
_save_editor_presentation = _NOT_LOOKED_UP


def get_save_editor_presentation():
    """The save editor's presentation module, or None when there isn't one.

    Looked up once - this runs from draw code, and a failed import isn't
    cached by Python, so trying again every redraw would hit the disk each time.
    """
    global _save_editor_presentation
    if _save_editor_presentation is _NOT_LOOKED_UP:
        try:
            _save_editor_presentation = importlib.import_module(
                SAVE_EDITOR_PRESENTATION, __package__
            )
        except ImportError:
            _save_editor_presentation = None
    return _save_editor_presentation


class VIEW3D_PT_nms_io_panel(bpy.types.Panel):
    """ Save Files Browser """

    bl_idname = "VIEW3D_PT_nms_io_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_label = "I/O"
    # Popovers size themselves from this rather than from their content.
    bl_ui_units_x = 14


    def draw(self, context):
        layout = self.layout
        nms_main = getattr(context.scene, "nms_main", None)
        drew_anything = False

        if operator_exists(CLIPBOARD_IMPORT_OP) and operator_exists(CLIPBOARD_EXPORT_OP):
            clipboard_box = layout.box().column(align=True)
            clipboard_box.label(text="Clipboard")
            clipboard_column = clipboard_box.row(align=False)
            clipboard_column.operator(CLIPBOARD_IMPORT_OP, icon="PASTEDOWN")
            clipboard_export_column = clipboard_column.column(align=True)
            clipboard_export_column.operator(CLIPBOARD_EXPORT_OP, icon="COPYDOWN")
            if nms_main is not None:
                clipboard_export_column.prop(nms_main, "check_export_objects_only", text="Objects Only")
            layout.separator()
            drew_anything = True

        save_editor_presentation = get_save_editor_presentation()
        if save_editor_presentation is not None:
            save_editor_presentation.draw_save_manager(layout, context)
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
    # Popovers size themselves from this rather than from their content.
    bl_ui_units_x = 13
    

    def draw(self, context):
        """Draw the Base Builder dropdown's contents into `layout`."""
        layout = self.layout
        
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
        proxy_row.operator(
            "object.nms_switch_proxies_to_low", text="Simple Proxies",
            icon="MESH_CUBE", depress=quality == "low",
        )
        proxy_row.operator(
            "object.nms_switch_proxies_to_high", text="High-res Proxies",
            icon="MESH_MONKEY", depress=quality == "high",
        )
        proxy_row.separator()
        proxy_row.operator("object.nms_fix_broken_textures", text="", icon="FILE_REFRESH")

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
        asset_browser_box.operator(
            "object.nms_launch_asset_browser_window", text="Launch Asset Browser", icon="ASSET_MANAGER"
        )
        
        recent_data = asset_browser.get_recent_objects_data()
        fav_data = asset_browser.get_favourite_objects_data()

        # Neither tab has anything to show yet - skip the whole section
        # (including the Favourites/Recent switcher) rather than offer a
        # toggle between two empty lists.
        if recent_data or fav_data:
            layout.separator()
            quick_access_column = layout.column(align = True)
            quick_access_column.label(text = "Quick Access")
            quick_access_column.row(align = True).prop(context.scene,"enum_assets_quick_access_view_mode", expand = True)
            quick_access_column.separator()


            def draw_assets(asset_data):
                if asset_data:
                    row = quick_access_column.row(align = True)
                    for subcategories, object_ids in asset_data.items():
                        asset_browser_presentation.draw_sub_category(
                            pcoll = pcoll,
                            container = row,
                            label = subcategories,
                            elements_list = object_ids,
                            number_of_columns = 4,
                            icon_size = 2,
                            grid_type = "Other",
                            show_title = False
                        )
                else:
                    quick_access_column.label(text="No Items")


            if enum_assets_quick_access_view_mode == "recent":
                if recent_data:
                    recent_first_four = dict(list(recent_data.items())[:4])
                    recent_dict = {"Recent Objects": recent_first_four}
                    draw_assets(recent_dict)
                else:
                    draw_assets(None)
            else:
                if fav_data:
                    fav_first_four = dict(list(fav_data.items())[:4])
                    fav_dict = {"Favourite Objects": fav_first_four}
                    draw_assets(fav_dict)
                else:
                    draw_assets(None)
        
        layout.separator()
        search_colun = layout.column(align = True)
        search_colun.label(text = "Search Items")
        search_colun.prop(asset_browser, "asset_broser_search_query", text="", icon='VIEWZOOM')
        
        if asset_browser.enum_asset_browser_what_to_display == "search":
            search_data = asset_browser.get_search_results()
            draw_assets(search_data)
                        


    
    
    