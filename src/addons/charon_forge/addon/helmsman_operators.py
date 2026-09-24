import bpy


class ImportShip(bpy.types.Operator):
    """Import a ship (dummy)"""

    bl_idname = "object.charon_import_ship"
    bl_label = "Import Ship"

    def execute(self, context):
        self.report({"INFO"}, "Import Ship (dummy)")
        return {"FINISHED"}


class ImportBatch(bpy.types.Operator):
    """List the ships in the batch ship file (dummy - nothing is placed yet)"""

    bl_idname = "object.charon_import_batch"
    bl_label = "Import Batch"

    def execute(self, context):
        helmsman = context.scene.charon_helmsman
        helmsman.refresh_batch_ship_reviews()
        helmsman.batch_list_visible = True
        return {"FINISHED"}


class ExportReviews(bpy.types.Operator):
    """Copy the review results to the clipboard (dummy format for now)"""

    bl_idname = "object.charon_export_reviews"
    bl_label = "Export"

    def execute(self, context):
        helmsman = context.scene.charon_helmsman

        # get_row_slot, so ships on other pages show the slot they were left on
        lines = [
            f"{ship.ship_name}: slot {helmsman.get_row_slot(index)}, {ship.review_status.title()}"
            for index, ship in enumerate(helmsman.batch_ship_reviews)
        ]
        context.window_manager.clipboard = "\n".join(lines)

        self.report({"INFO"}, f"Copied {len(helmsman.batch_ship_reviews)} ship(s) to clipboard")
        return {"FINISHED"}


class ExportResultFiles(bpy.types.Operator):
    """Export the review results to files (dummy - nothing is written out yet)"""

    bl_idname = "object.charon_export_result_files"
    bl_label = "Export Result Files"

    def execute(self, context):
        helmsman = context.scene.charon_helmsman
        self.report({"INFO"}, f"Exported {len(helmsman.batch_ship_reviews)} ship(s) to files (dummy)")
        return {"FINISHED"}


class ExportToSave(bpy.types.Operator):
    """Write every ship on the list that has a ship slot into the save file"""

    bl_idname = "object.charon_export_to_save"
    bl_label = "Export to Save"

    def _get_writable_rows(self, helmsman):
        """Rows that have a ship slot to be written to.

        Approve/Reject is only a review result for Export Results to
        Clipboard - it has no say in what is written here. An unchecked row
        is skipped outright.

        Reads slot_value rather than slot: slot is a dynamic enum stored as
        a number, and after the save's corvettes change that number can
        point at a different corvette until the rows are reassigned.
        """
        from ..utils import helmsman_utils

        return [
            (index, ship)
            for index, ship in enumerate(helmsman.batch_ship_reviews)
            if ship.included
            and ship.slot_value not in ("", helmsman_utils.NO_SLOT_ID)
        ]

    def invoke(self, context, event):
        helmsman = context.scene.charon_helmsman
        if not self._get_writable_rows(helmsman):
            self.report({"WARNING"}, "No ships with a ship slot to write to")
            return {"CANCELLED"}

        # this overwrites ship slots in the player's actual save file, so it
        # is worth a look before it happens rather than on one stray click
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        from ..utils import base_builder_utils, helmsman_utils

        helmsman = context.scene.charon_helmsman

        save_links = base_builder_utils.get_current_save_links()
        if save_links is None:
            self.report({"ERROR"}, "No save slot selected")
            return {"CANCELLED"}

        # the rows hold a user_data, which is what identifies a ship slot -
        # the BaseData behind it is what the save writer needs
        corvettes_by_user_data = {
            str(corvette.user_data): corvette
            for corvette in base_builder_utils.get_save_corvettes()
        }
        # matched by id, not position: the batch file is read again here, and
        # if it changed since Import Batch its ships may have moved
        batch_ships = helmsman_utils.get_batch_ships()
        batch_ships_by_id = {ship["id"]: ship for ship in batch_ships if ship["id"]}

        written = 0
        failures = []
        for index, ship in self._get_writable_rows(helmsman):
            corvette = corvettes_by_user_data.get(ship.slot_value)
            if corvette is None:
                failures.append(f"{ship.ship_name} (ship slot {ship.slot_value} is gone)")
                continue

            if ship.ship_id:
                batch_ship = batch_ships_by_id.get(ship.ship_id)
            else:
                batch_ship = batch_ships[index] if index < len(batch_ships) else None
            if batch_ship is None:
                failures.append(f"{ship.ship_name} (no longer in the batch file)")
                continue

            success, message = base_builder_utils.write_objects_to_corvette(
                batch_ship["objects"], corvette, save_links
            )
            if success:
                written += 1
            else:
                failures.append(f"{ship.ship_name}: {message}")

        # the corvette list the panel is showing came from the save file we
        # just wrote over, so it has to be re-read before it is used again
        if written:
            save_data = base_builder_utils.get_save_data()
            if save_data is not None:
                save_data.refresh_bases_list()
            helmsman.assign_slots()

        if failures:
            self.report(
                {"ERROR"},
                f"Wrote {written} ship(s), {len(failures)} failed - " + "; ".join(failures),
            )
            return {"FINISHED"}

        self.report({"INFO"}, f"Wrote {written} ship(s) to the save file")
        return {"FINISHED"}


class ToggleReviewStatus(bpy.types.Operator):
    """Set a row's review status, or clear it back to Pending on a re-click"""

    bl_idname = "object.charon_toggle_review_status"
    bl_label = "Toggle Review Status"

    row_index: bpy.props.IntProperty()
    status: bpy.props.StringProperty()

    def execute(self, context):
        helmsman = context.scene.charon_helmsman
        if self.row_index >= len(helmsman.batch_ship_reviews):
            return {"CANCELLED"}

        ship = helmsman.batch_ship_reviews[self.row_index]
        ship.review_status = "PENDING" if ship.review_status == self.status else self.status
        return {"FINISHED"}


class EditShipNote(bpy.types.Operator):
    """Write a note on this ship"""

    bl_idname = "object.charon_edit_ship_note"
    bl_label = "Ship Note"

    row_index: bpy.props.IntProperty()
    note: bpy.props.StringProperty(name="Note")

    def _get_ship(self, context):
        reviews = context.scene.charon_helmsman.batch_ship_reviews
        return reviews[self.row_index] if self.row_index < len(reviews) else None

    def invoke(self, context, event):
        ship = self._get_ship(context)
        if ship is None:
            return {"CANCELLED"}
        # start from the current note so an edit doesn't mean retyping it
        self.note = ship.note
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        self.layout.prop(self, "note", text="")

    def execute(self, context):
        ship = self._get_ship(context)
        if ship is None:
            return {"CANCELLED"}
        ship.note = self.note.strip()

        # the dialog closes over the panel without redrawing it, so the new
        # note would only show on the next mouse-over - redraw it now
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
        return {"FINISHED"}


class SetBatchPage(bpy.types.Operator):
    """Switch the batch ship list to a page, refilling its slots"""

    bl_idname = "object.charon_set_batch_page"
    bl_label = "Set Page"

    page: bpy.props.IntProperty(default=0)

    def execute(self, context):
        helmsman = context.scene.charon_helmsman
        helmsman.set_page(self.page)
        return {"FINISHED"}


class ResetReviews(bpy.types.Operator):
    """Clear the review list and start over"""

    bl_idname = "object.charon_reset_reviews"
    bl_label = "Reset"

    def execute(self, context):
        helmsman = context.scene.charon_helmsman
        helmsman.batch_ship_reviews.clear()
        helmsman.clear_stored_slots()
        helmsman.batch_list_visible = False
        return {"FINISHED"}


classes = (
    ImportShip,
    ImportBatch,
    ExportReviews,
    ExportResultFiles,
    ExportToSave,
    ToggleReviewStatus,
    EditShipNote,
    SetBatchPage,
    ResetReviews,
)
