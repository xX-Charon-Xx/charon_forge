import bpy
from bpy.types import Panel

from ..save_editor.save_manager import CharonSaveManager
from ..utils import base_builder_utils, helmsman_utils, icon_utils
from .helmsman_operators import (
    EditShipNote,
    ExportResultFiles,
    ExportReviews,
    ExportToSave,
    ImportBatch,
    ImportShip,
    ResetReviews,
    SetBatchPage,
    ToggleReviewStatus,
)


# Set once _load_save_accounts has run, so a load that fails (no save
# folder, lz4 could not be installed) is not retried on every redraw.
_accounts_load_attempted = False


def _load_save_accounts():
    """Timer callback - fill the account list once per session.

    The save editor fills it when its own panel is switched on; Helmsman has
    no such switch, so this does the same the first time the panel draws
    (draw() itself cannot write properties). That also installs the lz4
    module save files are read with, if it is missing - see
    save_editor_dependencies. Returns None so the timer does not repeat.
    """
    global _accounts_load_attempted
    _accounts_load_attempted = True
    save_data = base_builder_utils.get_save_data()
    if save_data is not None:
        try:
            save_data.on_check_plugin_enabled(bpy.context)
        except Exception as error:                        # noqa: BLE001
            print("Charon Forge: could not load save accounts: %r" % error)
    return None


def draw_save_slot_picker(layout, context):
    """Account / Save Slot, the same two dropdowns the Save Manager panel
    has at the top of its own picker - reading and writing Charon Forge's
    own scene.charon_save_data.
    """
    save_data = base_builder_utils.get_save_data()
    if save_data is None:
        layout.label(text="Save Manager unavailable", icon="ERROR")
        return

    if not CharonSaveManager.enum_accounts_list:
        if _accounts_load_attempted:
            layout.label(text="Could not load save accounts", icon="ERROR")
            return
        if not bpy.app.timers.is_registered(_load_save_accounts):
            bpy.app.timers.register(_load_save_accounts, first_interval=0.0)
        layout.label(text="Loading save accounts...", icon="TIME")
        return

    column = layout.column(align=True)
    column.scale_y = 1.2
    #column.label(text="Account / Save Slot")
    column.prop(save_data, "nms_account_selected", icon="COMMUNITY")
    column.prop(save_data, "nms_save_slot", icon="LINENUMBERS_ON")


def is_save_slot_selected(context):
    """Whether a real save slot is picked - "Default" is the placeholder
    "Select Save Slot" entry get_save_slots_list() puts at the top of the
    list in save_editor/save_manager.py, not an actual slot.
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

        # a change of save slot has to be noticed here: the save manager's
        # dropdown has no hook of ours to call - see
        # Helmsman.request_slot_reassign_if_save_changed
        helmsman.request_slot_reassign_if_save_changed()

        step_3_box = steps_column.box().column(align = True)
        step_3_box.label(text = "Step - 3 :   Load into Ship Slots")

        # the ship count shows even on a single page, the page number only
        # once there is more than one
        page_count = helmsman.get_page_count()
        ship_count = len(helmsman.batch_ship_reviews)
        # page number on the left, ship count on the right
        progress_row = step_3_box.row(align=True)
        page_side = progress_row.row(align=True)
        page_side.alignment = "LEFT"
        if page_count > 1:
            page_side.label(text=f"Page {helmsman.current_page + 1} of {page_count}")
        count_side = progress_row.row(align=True)
        count_side.alignment = "RIGHT"
        count_side.label(text=f"{ship_count} ship{'' if ship_count == 1 else 's'} imported")

        if page_count > 1:
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
                text=f"{unassigned_count} ship(s) on this page have no ship slot",
                icon="ERROR",
            )

        batch_list_column = step_3_box.column(align = True)
        for index, ship in helmsman.get_page_items():
            batch_list_element_box = batch_list_column.box()
            row = batch_list_element_box.row(align=True)
            #row.alignment = "LEFT"
            #row.label(text = f"{index}. ")
            #checkbox_row = row.row(align=True)
            #checkbox_row.scale_y = 1.5
            #checkbox_row.prop(ship, "included", text="")

            column = row.column(align = True)
            column.alert = ship.slot_bumped
            column.label(text=f"{ship.ship_name } ({ship.part_count} pts)")

            note_row = column.row(align=True)
            note_row.scale_y = 1.2
            note_row.alert = False
            note_edit = note_row.operator(
                EditShipNote.bl_idname, text="", icon="TEXT", emboss=True
            )
            note_edit.row_index = index
            note_row.label(text=ship.note or " No Note")

            # two lines tall, level with the name and note lines beside it
            options_row = row.row(align = True)
            options_row.scale_y = 2
            options_row.enabled = ship.included
            slot_row = options_row.row(align = True)
            slot_row.scale_x = 0.65
            slot_row.alert = ship.slot_value in ("", helmsman_utils.NO_SLOT_ID) or ship.slot_bumped
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
