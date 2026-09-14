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

        lines = [
            f"{ship.ship_name}: slot {ship.slot}, {ship.review_status.title()}"
            for ship in helmsman.batch_ship_reviews
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
    """Write every ship that has a ship slot into the save file"""

    bl_idname = "object.charon_export_to_save"
    bl_label = "Export to Save"

    def _get_writable_rows(self, helmsman):
        """Rows that have a ship slot to be written to.

        review_status is not consulted: approve/pending/reject is the user's
        note about a ship for the results export, not a say in whether it
        goes into the save. Only a row with nowhere to go is left out - see
        Helmsman.assign_slots.
        """
        from ..utils import helmsman_utils

        return [
            (index, ship)
            for index, ship in enumerate(helmsman.batch_ship_reviews)
            if ship.slot != helmsman_utils.NO_SLOT_ID
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
        batch_ships = helmsman_utils.get_batch_ships()

        written = 0
        failures = []
        for index, ship in self._get_writable_rows(helmsman):
            corvette = corvettes_by_user_data.get(ship.slot)
            if corvette is None or index >= len(batch_ships):
                failures.append(f"{ship.ship_name} (ship slot {ship.slot} is gone)")
                continue

            success, message = base_builder_utils.write_objects_to_corvette(
                batch_ships[index]["objects"], corvette, save_links
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


class ResetReviews(bpy.types.Operator):
    """Clear the review list and start over"""

    bl_idname = "object.charon_reset_reviews"
    bl_label = "Reset"

    def execute(self, context):
        helmsman = context.scene.charon_helmsman
        helmsman.batch_ship_reviews.clear()
        helmsman.batch_list_visible = False
        return {"FINISHED"}


classes = (
    ImportShip,
    ImportBatch,
    ExportReviews,
    ExportResultFiles,
    ExportToSave,
    ResetReviews,
)
