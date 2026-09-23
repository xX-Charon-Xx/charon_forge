from bpy.types import Panel

from ..utils import base_builder_utils, helmsman_utils, icon_utils
from .helmsman_operators import (
    ExportResultFiles,
    ExportReviews,
    ExportToSave,
    ImportBatch,
    ImportShip,
    ResetReviews,
    SetBatchPage,
    ToggleReviewStatus,
)


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

        # one outer column, aligned, so each step's box stacks flush against
        # the one before it rather than each floating with its own margins
        steps_column = layout.column(align = False)

        step_1_box = steps_column.box().column(align = True)
        step_1_box.label(text = "Step - 1 :  Account / Save-Slot")
        draw_save_slot_picker(step_1_box, context)

        if not is_save_slot_selected(context):
            return

        step_2_box = steps_column.box().column(align = True)
        step_2_box.label(text = "Step - 2 :   Select Files for Review")
        import_row = step_2_box.row(align=True)
        import_row.operator(ImportShip.bl_idname, text = "Load File")
        import_row.operator(ImportBatch.bl_idname, text = "Load Clipboard")

        helmsman = context.scene.charon_helmsman
        if not helmsman.batch_list_visible:
            return

        # a change of save slot has to be noticed here: the host addon's own
        # dropdown has no hook of ours to call - see
        # Helmsman.request_slot_reassign_if_save_changed
        helmsman.request_slot_reassign_if_save_changed()

        step_3_box = steps_column.box().column(align = True)
        step_3_box.label(text = "Step - 3 :   Load into Ship Slots")

        page_count = helmsman.get_page_count()
        if page_count > 1:
            progress_row = step_3_box.row(align=True)
            progress_row.alignment = "CENTER"
            progress_row.label(text=f"Page {helmsman.current_page + 1} of {page_count}")

            tabs_row = step_3_box.row(align=True)
            for page in range(page_count):
                tab = tabs_row.operator(
                    SetBatchPage.bl_idname,
                    text=str(page + 1),
                    depress=(page == helmsman.current_page),
                )
                tab.page = page

        unassigned_count = helmsman.get_unassigned_count()
        if unassigned_count:
            warning_column = step_3_box.column(align = True)
            warning_column.scale_y = 0.8
            warning_column.alert = True
            warning_column.label(
                text=f"{unassigned_count} ship(s) on this page have no free slot",
                icon="ERROR",
            )

        batch_list_column = step_3_box.column(align = True)
        for index, ship in helmsman.get_page_items():
            batch_list_element_box = batch_list_column.box()
            batch_list_element_box.scale_y = 0.6
            row = batch_list_element_box.row(align=True)
            #row.alignment = "LEFT"
            #row.label(text = f"{index}. ")
            checkbox_row = row.row(align=True)
            checkbox_row.scale_y = 1.5
            checkbox_row.prop(ship, "included", text="")

            column = row.column(align = True)
            column.alert = ship.slot_bumped
            column.label(text=ship.ship_name)
            column.label(text=f"{ship.part_count} parts")

            options_row = row.row(align = True)
            options_row.scale_y = 2
            options_row.enabled = ship.included
            slot_row = options_row.row(align = True)
            slot_row.scale_x = 0.65
            slot_row.alert = ship.slot == helmsman_utils.NO_SLOT_ID or ship.slot_bumped
            slot_row.prop(ship, "slot", text="")

            options_row.separator()

            buttons_row = options_row.row(align = True)
            buttons_row.scale_x = 1.2

            approve = buttons_row.operator(
                ToggleReviewStatus.bl_idname,
                text="",
                icon="CHECKMARK",
                depress=(ship.review_status == "APPROVE"),
            )
            approve.row_index = index
            approve.status = "APPROVE"

            reject_row = buttons_row.row(align = True)
            reject_row.alert = ship.review_status == "REJECT"
            reject = reject_row.operator(
                ToggleReviewStatus.bl_idname,
                text="",
                icon="X",
                depress=(ship.review_status == "REJECT"),
            )
            reject.row_index = index
            reject.status = "REJECT"

        # pad the last page with empty rows so every page takes up the same
        # space - otherwise a half-full last page shrinks the panel and the
        # page tabs above jump around as the user switches between pages
        page_size = helmsman.get_page_size()
        missing_rows = page_size - len(helmsman.get_page_items())
        for _ in range(max(0, missing_rows)):
            dummy_box = batch_list_column.box()
            dummy_box.scale_y = 0.6
            dummy_column = dummy_box.column(align=True)
            dummy_column.label(text="")
            dummy_column.label(text="")

        # nothing to write out or clear while the batch turned up no ships
        if not len(helmsman.batch_ship_reviews):
            return

        step_3_box.separator()
        export_reset_row = step_3_box.column(align = True)
        export_reset_row.operator(ExportToSave.bl_idname, text="Export to Save", icon="EXPORT")
        export_reset_row.operator(ResetReviews.bl_idname, text="Reset", icon="LOOP_BACK")

        step_4_box = steps_column.box().column(align = True)
        step_4_box.label(text = "Step - 4 :   Export Results")
        step_4_box.operator(ExportReviews.bl_idname, text="Export Results to Clipboard", icon="EXPORT")
        step_4_box.operator(ExportResultFiles.bl_idname, text="Export Result Files", icon="FILE_FOLDER")



classes = (
    CHARON_PT_helmsman_panel,
)
