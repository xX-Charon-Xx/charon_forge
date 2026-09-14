from bpy.types import Panel

from ..utils import base_builder_utils, helmsman_utils, icon_utils
from .helmsman_operators import ExportResultFiles, ExportReviews, ExportToSave, ImportBatch, ImportShip, ResetReviews


def draw_save_slot_picker(layout, context):
    """Account / Save Slot, the same two dropdowns the Save Manager panel
    has at the top of its own picker - reused rather than duplicated, since
    both read/write the host addon's own scene.nms_save_data.
    """
    save_data = base_builder_utils.get_save_data()
    if save_data is None:
        layout.label(text="Save Manager unavailable", icon="ERROR")
        return

    column = layout.column(align=True)
    column.scale_y = 1.2
    #column.label(text="Account / Save Slot")
    column.prop(save_data, "nms_account_selected", icon="COMMUNITY")
    column.prop(save_data, "nms_save_slot", icon="LINENUMBERS_ON")


def is_save_slot_selected(context):
    """Whether a real save slot is picked - "Default" is the placeholder
    "Select Save Slot" entry get_save_slots_list() puts at the top of the
    list in the host addon's save_manager.py, not an actual slot.
    """
    save_data = base_builder_utils.get_save_data()
    return save_data is not None and save_data.nms_save_slot != "Default"


# Helmsman Panel ---
class CHARON_PT_helmsman_panel(Panel):
    bl_idname = "CHARON_PT_helmsman_panel"
    bl_label = "Helmsman"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Charon Forge"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout
        
        
        description_row = layout.row(align = True)
        description_row.scale_y = 0.6
        description_icon_row = description_row.row(align = True)
        description_icon_row.scale_x = 1.1
        description_icon_row.template_icon(
            icon_value=icon_utils.get_icon_id("helmsman"),
            scale=3,
        )
        description_column = description_row.column(align=True)
        description_column.separator()
        description_column.label(text="For Importing and Reviewing of")
        description_column.label(text="ships efficiently")

        helmsman_column = layout.column(align = True)
        helmsman_column.label(text = "Step - 1 :  Account / Save-Slot")
        draw_save_slot_picker(helmsman_column, context)

        if not is_save_slot_selected(context):
            return

        helmsman_column.separator()
        helmsman_column.label(text = "Step - 2 :   Select Files for Review")
        import_row = helmsman_column.row(align=True)
        import_row.operator(ImportShip.bl_idname, text = "Load File")
        import_row.operator(ImportBatch.bl_idname, text = "Load Clipboard")

        helmsman = context.scene.charon_helmsman
        if not helmsman.batch_list_visible:
            return

        # a change of save slot has to be noticed here: the host addon's own
        # dropdown has no hook of ours to call - see
        # Helmsman.request_slot_reassign_if_save_changed
        helmsman.request_slot_reassign_if_save_changed()

        helmsman_column.separator()
        helmsman_column.label(text = "Step - 3 :   Load into Ship Slots")

        unassigned_count = helmsman.get_unassigned_count()
        if unassigned_count:
            warning_column = helmsman_column.column(align = True)
            warning_column.scale_y = 0.8
            warning_column.alert = True
            warning_column.label(
                text=f"{unassigned_count} ship(s) have no free slot",
                icon="ERROR",
            )

        batch_list_column = helmsman_column.column(align = True)
        for index, ship in enumerate(helmsman.batch_ship_reviews):
            batch_list_element_box = batch_list_column.box()
            batch_list_element_box.scale_y = 0.6
            row = batch_list_element_box.row(align=True)
            #row.alignment = "LEFT"
            #row.label(text = f"{index}. ")
            column = row.column(align = True)
            column.label(text=ship.ship_name)
            column.label(text=f"{ship.part_count} parts")

            options_row = row.row(align = True)
            options_row.scale_y = 2
            slot_row = options_row.row(align = True)
            slot_row.scale_x = 0.65
            slot_row.alert = ship.slot == helmsman_utils.NO_SLOT_ID
            slot_row.prop(ship, "slot", text="")
            
            options_row.separator()
            
            buttons_row = options_row.row(align = True)
            buttons_row.scale_x = 1.2
            buttons_row.prop_enum(ship, "review_status", "APPROVE")
            buttons_row.prop_enum(ship, "review_status", "PENDING")

            reject_row = buttons_row.row(align = True)
            reject_row.alert = ship.review_status == "REJECT"
            reject_row.prop_enum(ship, "review_status", "REJECT")


        # nothing to write out or clear while the batch turned up no ships
        if not len(helmsman.batch_ship_reviews):
            return

        helmsman_column.separator()
        export_reset_row = helmsman_column.column(align = True)
        export_reset_row.operator(ExportToSave.bl_idname, text="Export to Save", icon="EXPORT")
        export_reset_row.operator(ResetReviews.bl_idname, text="Reset", icon="LOOP_BACK")

        helmsman_column.separator()
        helmsman_column.label(text = "Step - 4 :   Export Results")
        helmsman_column.operator(ExportReviews.bl_idname, text="Export Results to Clipboard", icon="EXPORT")
        helmsman_column.operator(ExportResultFiles.bl_idname, text="Export Result Files", icon="FILE_FOLDER")



classes = (
    CHARON_PT_helmsman_panel,
)
