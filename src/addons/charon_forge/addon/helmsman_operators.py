import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper

from ..utils import helmsman_utils


def _load_batch_text(operator, context, text, source):
    """Validate a batch and fill the review list from it.

    Nothing is changed when it fails validation - the list the user already
    has stays as it was.
    """
    try:
        ships = helmsman_utils.parse_batch(text)
    except helmsman_utils.BatchError as error:
        operator.report({"ERROR"}, f"The {source} is not a valid ship batch: {error}")
        return {"CANCELLED"}

    context.scene.charon_helmsman.load_batch(ships)
    operator.report({"INFO"}, f"Loaded {len(ships)} ship(s) from the {source}")
    return {"FINISHED"}


def _collect_results(operator, helmsman):
    """The approved/rejected ships as a batch, or None (reported) if there
    are none - see helmsman_utils.build_results."""
    rows = []
    for item in helmsman.batch_ship_reviews:
        if item.review_status not in helmsman_utils.REVIEW_TO_APPROVAL:
            continue
        ship = helmsman.get_ship_data(item)
        if ship is None:
            operator.report({"WARNING"}, f"{item.ship_name}: its batch data is missing, left out")
            continue
        rows.append((ship, item.review_status, item.note))

    results = helmsman_utils.build_results(rows)
    if not results:
        operator.report({"WARNING"}, "No approved or rejected ships to export")
        return None
    return results


class ImportBatchFile(bpy.types.Operator, ImportHelper):
    """Load a batch of ships to review from a .json or .txt file"""

    bl_idname = "object.charon_import_batch_file"
    bl_label = "Load Batch File"

    filter_glob: bpy.props.StringProperty(default="*.json;*.txt", options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        try:
            with open(self.filepath, "r", encoding="utf-8-sig") as batch_file:
                text = batch_file.read()
        except (OSError, UnicodeDecodeError) as error:
            self.report({"ERROR"}, f"Could not read the file: {error}")
            return {"CANCELLED"}
        return _load_batch_text(self, context, text, "file")


class ImportBatchClipboard(bpy.types.Operator):
    """Load a batch of ships to review from the clipboard"""

    bl_idname = "object.charon_import_batch"
    bl_label = "Load Batch from Clipboard"

    def execute(self, context):
        return _load_batch_text(self, context, context.window_manager.clipboard, "clipboard")


class ExportReviews(bpy.types.Operator):
    """Copy the approved and rejected ships (id, status and note) to the clipboard"""

    bl_idname = "object.charon_export_reviews"
    bl_label = "Export Results to Clipboard"

    def execute(self, context):
        results = _collect_results(self, context.scene.charon_helmsman)
        if results is None:
            return {"CANCELLED"}

        context.window_manager.clipboard = helmsman_utils.dump_results(results)
        self.report({"INFO"}, f"Copied {len(results)} ship(s) to the clipboard")
        return {"FINISHED"}


class ExportResultFiles(bpy.types.Operator, ExportHelper):
    """Save the approved and rejected ships (id, status and note) to a .json file"""

    bl_idname = "object.charon_export_result_files"
    bl_label = "Export Results to File"

    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json;*.txt", options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        results = _collect_results(self, context.scene.charon_helmsman)
        if results is None:
            return {"CANCELLED"}

        try:
            with open(self.filepath, "w", encoding="utf-8") as results_file:
                results_file.write(helmsman_utils.dump_results(results))
        except OSError as error:
            self.report({"ERROR"}, f"Could not write the file: {error}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Saved {len(results)} ship(s) to {self.filepath}")
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
        failures = []
        to_write = []   # (ship row, objects, corvette)
        for index, ship in self._get_writable_rows(helmsman):
            corvette = corvettes_by_user_data.get(ship.slot_value)
            if corvette is None:
                failures.append(f"{ship.ship_name} (ship slot {ship.slot_value} is gone)")
                continue

            # the parts come off the row itself, stored when it was loaded
            batch_ship = helmsman.get_ship_data(ship)
            if batch_ship is None:
                failures.append(f"{ship.ship_name} (its batch data is missing)")
                continue

            to_write.append((ship, batch_ship["objects"], corvette))

        # every ship goes into the save in one go: each save file is read,
        # backed up and written once, rather than once per ship
        written = 0
        if to_write:
            written_indices, write_failures, _ = base_builder_utils.write_objects_to_corvettes(
                [(objects, corvette) for _, objects, corvette in to_write],
                save_links,
            )
            written = len(written_indices)
            for index, reason in write_failures.items():
                failures.append(f"{to_write[index][0].ship_name}: {reason}")

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


class ImportReviewShip(bpy.types.Operator):
    """Build this ship's parts in the scene"""

    bl_idname = "object.charon_import_review_ship"
    bl_label = "Import Ship"
    bl_options = {"REGISTER", "UNDO"}

    row_index: bpy.props.IntProperty()

    def execute(self, context):
        from ..builder import get_builder
        from ..utils import nmsship

        helmsman = context.scene.charon_helmsman
        if self.row_index >= len(helmsman.batch_ship_reviews):
            return {"CANCELLED"}

        item = helmsman.batch_ship_reviews[self.row_index]
        ship = helmsman.get_ship_data(item)
        if ship is None:
            self.report({"ERROR"}, f"{item.ship_name}: its batch data is missing")
            return {"CANCELLED"}

        objects = ship.get("objects") or []
        get_builder().deserialise_from_data(
            {"Objects": objects, "BaseVersion": nmsship.DEFAULT_BASE_VERSION}
        )
        self.report({"INFO"}, f"Imported {item.ship_name} ({len(objects)} parts)")
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
    ImportBatchFile,
    ImportBatchClipboard,
    ExportReviews,
    ExportResultFiles,
    ExportToSave,
    ToggleReviewStatus,
    ImportReviewShip,
    EditShipNote,
    SetBatchPage,
    ResetReviews,
)
