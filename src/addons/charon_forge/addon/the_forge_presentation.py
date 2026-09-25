from bpy.types import Panel

from ..objects.sphere import Sphere
from ..utils import icon_utils
from .the_forge_operators import CreateSphere, SplitSphere, sphere_source_problem


# The Forge Panel ---
class CHARON_PT_the_forge_panel(Panel):
    bl_idname = "CHARON_PT_the_forge_panel"
    bl_label = "The Forge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Charon Forge"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout

        # laid out like the crossing/optimiser panels: the icon on the left,
        # the description and controls in a column beside it
        description_row = layout.row(align=True)
        description_row.scale_y = 0.6
        description_icon_row = description_row.row(align=True)
        description_icon_row.scale_x = 1.1
        description_icon_row.template_icon(
            icon_value=icon_utils.get_icon_id("the_forge"),
            scale=3,
        )
        description_column = description_row.column(align=True)
        description_column.separator()
        description_column.label(text="Forge new parts and")
        description_column.label(text="shape them into ships")

        layout.separator()
        box = layout.box()
        active_object = context.active_object
        if Sphere.is_sphere(active_object):
            draw_sphere_settings(box, active_object.charon_sphere)
            row = box.row()
            #row.scale_y = 2
            row.operator(SplitSphere.bl_idname, icon="MOD_EXPLODE")
            return

        problem = sphere_source_problem(active_object)
        if problem:
            box.label(text=problem, icon="INFO")
        else:
            box.label(text=f"Part: {active_object.name}", icon="OBJECT_DATA")
        row = box.row()
        #row.scale_y = 2
        row.operator(CreateSphere.bl_idname, icon="MESH_UVSPHERE")


# what the rings and segments counts are called in each topology; None hides
# one it doesn't use
_COUNT_LABELS = {
    "RINGS": ("Rings", "Around"),
    "MERIDIANS": ("Along", "Meridians"),
    "GEODESIC": ("Frequency", None),
    "CUBE": ("Grid", None),
    "SPIRAL": (None, "Copies"),
}


def draw_sphere_settings(layout, forge):
    """The settings of the active sphere."""
    layout.label(text=f"Sphere of {forge.object_id}", icon="MESH_UVSPHERE")
    
    topology_col = layout.column(align = True)
    topology_col.label(text = "Sphere")
    topology_col.prop(forge, "topology", text="")

    column = layout.column(align=True)
    column.prop(forge, "radius")
    column.prop(forge, "tile_scale")
    rings_label, segments_label = _COUNT_LABELS.get(forge.topology, ("Rings", "Around"))
    
    
    ring_seg_row = column.row(align = True)
    if rings_label:
        ring_seg_row.prop(forge, "rings", text=rings_label)
    if segments_label:
        ring_seg_row.prop(forge, "segments", text=segments_label)

    column = layout.column(align=True)
    density_scale_row = column.row(align = True)
    if forge.topology == "RINGS":
        density_scale_row.prop(forge, "pole_density")
    

    column = layout.column(align=True)
    top_bottom_col = column.row(align = True)
    top_bottom_col.prop(forge, "top")
    top_bottom_col.prop(forge, "bottom")
    column.prop(forge, "sweep")

    column.separator()
    column.label(text = "Part Orientation")
    column.row(align=True).prop(forge, "rotation", text = "")
    #if forge.topology == "RINGS":
    #    layout.prop(forge, "stagger", toggle=True)

    if forge.message:
        layout.label(text=forge.message, icon="ERROR")
    else:
        layout.label(text=f"{forge.part_count} parts", icon="INFO")


classes = (
    CHARON_PT_the_forge_panel,
)
