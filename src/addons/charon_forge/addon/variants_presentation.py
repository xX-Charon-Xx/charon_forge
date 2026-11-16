from bpy.types import Panel

from ..utils import dictionary, icon_utils
from .variants_operators import ReplaceWithVariant, part_model_id


def _nice_name(object_id, nice_names):
    name = nice_names.get(object_id)
    return dictionary.to_title_case(name) if name else object_id


# Variants Panel ---
class CHARON_PT_variants_panel(Panel):
    bl_idname = "CHARON_PT_variants_panel"
    bl_label = "Variants"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Charon Forge"
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout

        current_id = part_model_id(context.active_object)
        if current_id is None:
            layout.label(text="Make a part active to see its variants", icon="INFO")
            return

        nice_names = dictionary.get_nice_names_diictionary()
        family = dictionary.get_variant_family(current_id)

        header = layout.box().column(align=True)
        header.label(text=_nice_name(current_id, nice_names), icon="OBJECT_DATA")
        header.label(text=f"ObjectID : {current_id}")

        if len(family) <= 1:
            layout.label(text="This part has no variants", icon="INFO")
            return

        layout.label(text=f"{len(family)} in this family - click one to swap", icon="PRESET")

        try:
            pcoll = icon_utils.get_asset_icons_pcoll()
        except KeyError:
            pcoll = None

        column = layout.column(align=True)
        column.scale_y = 1.2
        main_id = family[0]
        for variant_id in family:
            text = _nice_name(variant_id, nice_names)
            if variant_id == main_id:
                text += "  (Main)"
            icon_args = (
                {"icon_value": pcoll[variant_id].icon_id}
                if pcoll is not None and variant_id in pcoll
                else {"icon": "DOT"}
            )
            button = column.operator(
                ReplaceWithVariant.bl_idname,
                text=text,
                depress=(variant_id == current_id),
                **icon_args,
            )
            button.object_id = variant_id


classes = (
    CHARON_PT_variants_panel,
)
