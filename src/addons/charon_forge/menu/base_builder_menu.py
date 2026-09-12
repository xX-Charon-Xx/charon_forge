import bpy
from bpy.props import EnumProperty

from .. import addon_preferences
from ..utils import icon_utils
from . import base_builder_menu_operators
from .base_builder_menu_presentation import (EXPORT_PINNED_BASE_OP,
                                             VIEW3D_PT_nms_base_builder,
                                             VIEW3D_PT_nms_io_panel,
                                             get_save_editor_presentation,
                                             operator_exists)

@bpy.app.handlers.persistent
def apply_default_proxy_quality(_dummy):
    """Match the file just opened to the preferences page's default quality.

    Runs on every blend file load - including File > New, which fires
    load_post the same as opening a saved file - so a scene never sits at the
    "wrong" proxy quality (and the base builder addon at the "wrong" active
    builder) for what the user configured in Charon Forge's preferences.

    Does nothing while the "Auto Switch on Open" toggle is off, leaving an
    opened file at whatever quality it was saved at.
    """
    prefs = addon_preferences.get_addon_preferences()
    if prefs is None or not prefs.auto_switch_on_open:
        return

    context = bpy.context
    scene = context.scene
    if scene is None or not hasattr(scene, "enum_proxy_quality"):
        return

    # set_proxy_quality records the result on the scene itself, so the
    # dropdown comes up showing what the file was just switched to.
    base_builder_menu_operators.set_proxy_quality(
        context, prefs.default_proxy_quality == "high"
    )


def draw_header_menu(self, context):
    """Appended to VIEW3D_MT_editor_menus, which draws the header's menu row. """
    layout = self.layout

    layout.separator(factor = 5)
    menu_row = layout.box().row(align = True)
    menu_row.popover(panel=VIEW3D_PT_nms_base_builder.bl_idname, text="Charon",  icon_value = icon_utils.get_icon_id("app_icon"))



classes = (
    VIEW3D_PT_nms_base_builder,
    VIEW3D_PT_nms_io_panel
)


def register_menu():
    unregister_menu()
    bpy.types.VIEW3D_MT_editor_menus.append(draw_header_menu)

    bpy.types.Scene.enum_assets_quick_access_view_mode = EnumProperty(
        name="View Mode",
        description="Asset QA View Mode",
        items = [
            ("fav", "Favourites", "fav","HEART", 0),
            ("recent", "Recent", "recent","MOD_TIME",1)
        ],
        default = "fav"
    )

    # Which quality this scene was last switched to. Written by
    # base_builder_menu_operators.set_proxy_quality rather than driving it:
    # an update callback here would have to run the switch from inside a
    # property write, where blender does not let an operator's edits stick.
    # The two buttons in the Base Builder dropdown are drawn from it instead.
    bpy.types.Scene.enum_proxy_quality = EnumProperty(
        name="Proxy Quality",
        description="Which mesh source placed parts use, in the scene and for anything built afterwards",
        items=[
            ("low", "Simple Proxies", "Use the old fbx proxies from the models folder", "MESH_CUBE", 0),
            ("high", "High-res Proxies", "Use the high res library, where a part has one", "MESH_MONKEY", 1),
        ],
        default="high",
    )

    if apply_default_proxy_quality not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(apply_default_proxy_quality)


def unregister_menu():
    try:
        bpy.types.VIEW3D_MT_editor_menus.remove(draw_header_menu)
    except (ValueError, AttributeError, RuntimeError):
        # Not appended in the first place, which is fine - this runs on
        # unregister paths that may not have got as far as adding it.
        pass

    if apply_default_proxy_quality in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(apply_default_proxy_quality)

    if hasattr(bpy.types.Scene, "enum_assets_quick_access_view_mode"):
        del bpy.types.Scene.enum_assets_quick_access_view_mode

    if hasattr(bpy.types.Scene, "enum_proxy_quality"):
        del bpy.types.Scene.enum_proxy_quality
