import webbrowser

import bpy

# placeholder links, replace with the real ones
CHARON_GG_URL = "https://charon.gg/"
DISCORD_URL = "https://discord.gg/gW2AvwTwym"
SUPPORT_URL = "https://example.com/charon-forge/support"


class VisitGuides(bpy.types.Operator):
    """Visit Charon.gg."""

    bl_idname = "object.charon_visit_guides"
    bl_label = "Visit Charon.gg"

    def execute(self, context):
        webbrowser.open_new(CHARON_GG_URL)
        return {"FINISHED"}


class VisitDiscord(bpy.types.Operator):
    """Join the community discord."""

    bl_idname = "object.charon_visit_community"
    bl_label = "Join Discord"

    def execute(self, context):
        webbrowser.open_new(DISCORD_URL)
        return {"FINISHED"}


class VisitSupport(bpy.types.Operator):
    """Open the support page."""

    bl_idname = "object.charon_visit_support"
    bl_label = "Support"

    def execute(self, context):
        webbrowser.open_new(SUPPORT_URL)
        return {"FINISHED"}


class SwitchWorkspace(bpy.types.Operator):
    """Switch to a simpler workspace, or back to how blender was before"""

    bl_idname = "object.charon_cleanup_workspace"
    bl_label = "Switch Workspace"

    def execute(self, context):
        header = context.scene.charon_header
        if header.toggle_workspace():
            self.report({"INFO"}, "Workspace simplified (dummy)")
        else:
            self.report({"INFO"}, "Workspace restored (dummy)")
        return {"FINISHED"}


class Forge(bpy.types.Operator):
    """Dummy action, counts how many times it was pressed"""

    bl_idname = "object.charon_forge"
    bl_label = "Forge"

    def execute(self, context):
        header = context.scene.charon_header
        count = header.forge()
        self.report({"INFO"}, f"Forged {count} time(s)")
        return {"FINISHED"}


classes = (
    VisitGuides,
    VisitDiscord,
    VisitSupport,
    SwitchWorkspace,
    Forge,
)
