import json

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, PointerProperty

from . import helmsman_operators, helmsman_presentation
from ..utils import helmsman_utils

# a row's slot when the save has no corvette left for it
NO_SLOT_ID = helmsman_utils.NO_SLOT_ID
NO_SLOT_LABEL = helmsman_utils.NO_SLOT_LABEL

# kept at module level: Blender can crash if enum item strings get garbage collected
_slot_enum_items = []

# the "None" entry's number, far past any real corvette position
NO_SLOT_NUMBER = 100000


def get_slot_enum_items(self, context):
    """One entry per corvette in the save, grouped into free and in use, plus "None".
    The row's own slot and "None" are always listed, or Blender can't draw or keep the value."""
    global _slot_enum_items

    from ..utils import base_builder_utils

    helmsman = getattr(context.scene, "charon_helmsman", None) if context.scene else None

    # slot_value, not slot: reading slot would re-enter this callback
    taken_by = {}
    if helmsman is not None:
        for _, item in helmsman.get_page_items():
            if item == self or item.slot_value in ("", NO_SLOT_ID):
                continue
            taken_by[item.slot_value] = item.ship_name

    # numbers come from the save's order, so stored slots don't shift when the grouping changes
    corvettes = base_builder_utils.get_save_corvettes()
    free_items = []
    used_items = []
    for position, corvette in enumerate(corvettes):
        slot_id = str(corvette.user_data)
        holder = taken_by.get(slot_id)
        if holder is None:
            free_items.append((slot_id, slot_id, "", position))
        else:
            used_items.append((slot_id, slot_id, f"In use by {holder}", position))

    _slot_enum_items = []
    if free_items:
        _slot_enum_items.append(("", "Slots Free", ""))
        _slot_enum_items.extend(free_items)
    if used_items:
        _slot_enum_items.append(("", "Slots In Use", ""))
        _slot_enum_items.extend(used_items)
    _slot_enum_items.append(None)
    _slot_enum_items.append(
        (NO_SLOT_ID, NO_SLOT_LABEL, "Leave this ship out of the export", NO_SLOT_NUMBER)
    )
    return _slot_enum_items


# one enum, so a row is only ever in one state
REVIEW_STATUS_ITEMS = [
    ("APPROVE", "", "Approve this ship", "CHECKMARK", 0),
    ("PENDING", "", "Leave this ship pending", "SORTTIME", 1),
    ("REJECT", "", "Reject this ship", "X", 2),
]


# set while assign_slots writes rows, so their update callbacks stay quiet
_assigning_slots = False


def _on_slot_changed(self, context):
    """Take the slot just picked away from any other row on the page."""
    if _assigning_slots:
        return

    picked = self.slot
    self.slot_bumped = False
    self.slot_value = picked

    helmsman = getattr(context.scene, "charon_helmsman", None)
    if helmsman is None:
        return
    if picked != NO_SLOT_ID:
        helmsman.steal_slot_from_other_rows(self, picked)
    helmsman.store_page_slots()


class BatchShipReviewItem(bpy.types.PropertyGroup):
    """One row of the batch ship review list, filled in by Helmsman.load_batch."""

    ship_id: bpy.props.StringProperty()
    ship_name: bpy.props.StringProperty()
    part_count: IntProperty()
    # the ship's whole batch entry as JSON, kept here as its source may be gone by export
    ship_json: bpy.props.StringProperty()
    slot: EnumProperty(items=get_slot_enum_items, name="Slot", update=_on_slot_changed)
    # plain-string copy of slot, read by get_slot_enum_items so it doesn't recurse
    slot_value: bpy.props.StringProperty()
    review_status: EnumProperty(
        items=REVIEW_STATUS_ITEMS, name="Review Status", default="PENDING"
    )
    # unchecked keeps the row but leaves it out of export and review
    included: BoolProperty(default=True)

    # set for one redraw when another row took this row's slot
    slot_bumped: BoolProperty(default=False)

    # The reviewer's note on this ship, entered through EditShipNote.
    note: bpy.props.StringProperty(name="Note")


def _reassign_slots():
    """Timer callback: redo the slot assignments for a new save. Runs once."""
    scene = getattr(bpy.context, "scene", None)
    helmsman = getattr(scene, "charon_helmsman", None) if scene else None
    if helmsman is not None and len(helmsman.batch_ship_reviews):
        helmsman.clear_stored_slots()
        helmsman.assign_slots()
    return None


# State for the helmsman panel, stored on the scene as scene.charon_helmsman.
class Helmsman(bpy.types.PropertyGroup):

    # Dummy for now - nothing acts on it yet.
    is_active: BoolProperty(
        name="Helmsman Active",
        description="Whether the helmsman is currently steering",
        default=False,
    )

    # dummy value, counts how many times the steer button was pressed
    steer_count: IntProperty(
        name="Steer Count",
        default=0,
        min=0,
    )

    # Whether the batch ship list is showing - set by load_batch.
    batch_list_visible: BoolProperty(default=False)

    # rows for the batch ship review list, filled in by load_batch
    batch_ship_reviews: CollectionProperty(type=BatchShipReviewItem)

    # the save slot the assignments were made against, to notice a change
    assigned_save_slot: bpy.props.StringProperty()

    # the page showing; each page holds as many ships as the save has corvettes
    current_page: IntProperty(default=0, min=0)

    # every row's slot as JSON {row index: slot id}, so pages keep their slots
    stored_slots_json: bpy.props.StringProperty(default="{}")

    def toggle_active(self):
        self.is_active = not self.is_active
        return self.is_active

    def steer(self):
        self.steer_count += 1
        return self.steer_count

    def load_batch(self, ships):
        """Rebuild the review rows from helmsman_utils.parse_batch's ships."""
        from ..utils import helmsman_utils

        self.batch_ship_reviews.clear()
        self.current_page = 0
        self.clear_stored_slots()

        for ship in ships:
            item = self.batch_ship_reviews.add()
            item.ship_id = ship["id"]
            item.ship_name = ship["name"]
            item.part_count = len(ship["objects"])
            item.ship_json = json.dumps(ship, ensure_ascii=False)
            item.review_status = helmsman_utils.get_review_status(ship)
            item.note = ship.get("note", "").strip()

        self.batch_list_visible = True
        self.assign_slots()

    @staticmethod
    def get_ship_data(item):
        """A row's ship entry as loaded, or None if it cannot be read."""
        try:
            ship = json.loads(item.ship_json)
        except ValueError:
            return None
        return ship if isinstance(ship, dict) else None

    def get_page_size(self):
        """How many ships one page holds - one per corvette in the save.
        0 means no paging: one page holds everything."""
        from ..utils import base_builder_utils

        return len(base_builder_utils.get_save_corvettes())

    def get_page_count(self):
        """How many pages the batch list needs, at least 1."""
        page_size = self.get_page_size()
        total = len(self.batch_ship_reviews)
        if page_size <= 0 or total == 0:
            return 1
        return -(-total // page_size)  # ceil division

    def get_page_items(self):
        """(index, item) pairs for the rows on the current page."""
        page_size = self.get_page_size()
        if page_size <= 0:
            return list(enumerate(self.batch_ship_reviews))

        start = self.current_page * page_size
        end = start + page_size
        return list(enumerate(self.batch_ship_reviews))[start:end]

    def set_page(self, page):
        """Switch to a page, clamped to what exists, and bring back its slots."""
        self.store_page_slots()
        page_count = self.get_page_count()
        self.current_page = max(0, min(page, page_count - 1))
        self.assign_slots()

    # Stored slots ---
    def get_stored_slots(self):
        """{row index (str): slot id} - see stored_slots_json."""
        try:
            stored = json.loads(self.stored_slots_json or "{}")
        except ValueError:
            return {}
        return stored if isinstance(stored, dict) else {}

    def store_page_slots(self):
        """Record the current page's slots into stored_slots_json."""
        stored = self.get_stored_slots()
        for index, item in self.get_page_items():
            stored[str(index)] = item.slot_value or NO_SLOT_ID
        self.stored_slots_json = json.dumps(stored)

    def clear_stored_slots(self):
        self.stored_slots_json = "{}"

    def get_row_slot(self, index):
        """A row's slot id, whether or not its page is showing."""
        for page_index, item in self.get_page_items():
            if page_index == index:
                return item.slot_value or NO_SLOT_ID
        return self.get_stored_slots().get(str(index), NO_SLOT_ID)

    def assign_slots(self):
        """Give each row on the page its stored slot, or the first free corvette in save order.
        Rows on other pages are left on NO_SLOT_ID; their slots stay in stored_slots_json."""
        global _assigning_slots
        from ..utils import base_builder_utils

        corvette_ids = [
            str(corvette.user_data) for corvette in base_builder_utils.get_save_corvettes()
        ]
        stored = self.get_stored_slots()
        page_items = self.get_page_items()

        # work out the whole page first, then write it
        chosen = {}
        taken = set()
        for index, _ in page_items:
            slot_id = stored.get(str(index))
            if slot_id == NO_SLOT_ID:
                chosen[index] = slot_id
            elif slot_id in corvette_ids and slot_id not in taken:
                chosen[index] = slot_id
                taken.add(slot_id)
        free_ids = [slot_id for slot_id in corvette_ids if slot_id not in taken]
        for index, _ in page_items:
            if index not in chosen:
                chosen[index] = free_ids.pop(0) if free_ids else NO_SLOT_ID

        _assigning_slots = True
        try:
            # clear slot_value too, so the free/in-use grouping uses the new assignment
            for item in self.batch_ship_reviews:
                item.slot_value = NO_SLOT_ID
                item.slot = NO_SLOT_ID
                item.slot_bumped = False

            for index, item in page_items:
                item.slot_value = chosen[index]
                item.slot = chosen[index]
        finally:
            _assigning_slots = False

        self.store_page_slots()

        save_data = base_builder_utils.get_save_data()
        self.assigned_save_slot = save_data.nms_save_slot if save_data else ""

    def steal_slot_from_other_rows(self, changed_item, slot):
        """Clear `slot` off every other row on the page and flag those rows.
        Two rows on one corvette would overwrite each other on export."""
        for _, item in self.get_page_items():
            if item == changed_item:
                continue
            # slot_value, not slot: reading slot here would re-enter get_slot_enum_items
            if item.slot_value == slot:
                item.slot_value = NO_SLOT_ID
                item.slot = NO_SLOT_ID
                item.slot_bumped = True

    def get_unassigned_count(self):
        """How many rows on the current page the save has no corvette for."""
        return sum(
            1 for _, item in self.get_page_items()
            if item.slot_value in ("", NO_SLOT_ID)
        )

    def request_slot_reassign_if_save_changed(self):
        """Redo the assignments on a timer once the save slot changes.
        Called from draw(), which can't write, so the work runs after the redraw."""
        from ..utils import base_builder_utils

        save_data = base_builder_utils.get_save_data()
        if save_data is None or save_data.nms_save_slot == self.assigned_save_slot:
            return

        if bpy.app.timers.is_registered(_reassign_slots):
            return
        bpy.app.timers.register(_reassign_slots, first_interval=0.0)


classes = (
    BatchShipReviewItem,
    Helmsman,
) + helmsman_operators.classes + helmsman_presentation.classes


def register():
    for _class in classes:
        bpy.utils.register_class(_class)
    bpy.types.Scene.charon_helmsman = PointerProperty(type=Helmsman)


def unregister():
    del bpy.types.Scene.charon_helmsman
    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)
