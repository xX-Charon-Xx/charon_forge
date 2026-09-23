import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, PointerProperty

from . import helmsman_operators, helmsman_presentation
from ..utils import helmsman_utils

# What a row's slot shows when the save has no corvette left for it. A batch
# can hold more ships than the save has ship slots, and those rows still get
# listed rather than dropped - see get_slot_enum_items. Defined in
# helmsman_utils so the panel can read it without importing this module.
NO_SLOT_ID = helmsman_utils.NO_SLOT_ID
NO_SLOT_LABEL = helmsman_utils.NO_SLOT_LABEL

# kept alive at module level: an EnumProperty items callback must return a
# list backed by something other than a local, or blender can crash once the
# strings it built are garbage collected - same reason
# addon_preferences._theme_enum_items exists.
_slot_enum_items = []


def get_slot_enum_items(self, context):
    """One entry per corvette in the selected save slot, split into a
    "Slots Free" group and a "Slots In Use" group, plus a "None" entry to
    opt the row out of export entirely.

    Keyed by user_data, which is the corvette's position in the player's
    ship slots - see save_editor_utils.BaseData in the host addon, whose
    corvette list is already sorted by it. "In use" means another row on
    the same page already has that slot - see Helmsman.get_page_items;
    picking one of those bumps the row holding it.

    The row's own current slot stays in the list. Leaving it out looks
    tempting - re-picking what you already have does nothing - but Blender
    resolves a row's stored value against these items to draw the dropdown
    at all, so dropping it breaks both the display and every assignment
    that passes through it. It is grouped under "Slots Free", since from
    this row's point of view that is what it is.

    "None" (NO_SLOT_ID) is always present, so a row can be explicitly taken
    out of the export regardless of whether the save has a free corvette
    for it. Blender drops an enum value that is not in this list, and
    without it such a row would silently fall back to the first corvette -
    the one failure mode worth avoiding here, since it would export a ship
    over a slot nobody chose.
    """
    global _slot_enum_items

    from ..utils import base_builder_utils

    helmsman = getattr(context.scene, "charon_helmsman", None) if context.scene else None

    # reads slot_value rather than slot: slot is this same dynamic enum on
    # every other row too, and resolving it here would re-enter this very
    # callback for each of them - see BatchShipReviewItem.slot_value.
    taken_by = {}
    if helmsman is not None:
        for _, item in helmsman.get_page_items():
            if item == self or item.slot_value in ("", NO_SLOT_ID):
                continue
            taken_by[item.slot_value] = item.ship_name

    # every entry carries an explicit number, and that number comes from the
    # corvette's position in the save rather than from where the entry lands
    # in this list. Blender stores an enum as its number, so letting the
    # numbers fall out of the list order would silently repoint every row's
    # stored slot each time the free/in-use split changed under it.
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
        (NO_SLOT_ID, NO_SLOT_LABEL, "Leave this ship out of the export", len(corvettes))
    )
    return _slot_enum_items


# Approve/Pending/Reject as one enum instead of three separate buttons, so
# a row can only ever be in one of the three states - see
# BatchShipReviewItem.review_status.
REVIEW_STATUS_ITEMS = [
    ("APPROVE", "", "Approve this ship", "CHECKMARK", 0),
    ("PENDING", "", "Leave this ship pending", "SORTTIME", 1),
    ("REJECT", "", "Reject this ship", "X", 2),
]


def _on_slot_changed(self, context):
    """Bump any other row on the current page off the slot just picked.

    Two rows pointing at the same corvette would silently overwrite each
    other's ship on export, so a slot picked here is taken away from
    whichever other row on the page was holding it - see Helmsman.
    steal_slot_from_other_rows.
    """
    picked = self.slot
    self.slot_bumped = False
    self.slot_value = picked

    if picked == NO_SLOT_ID:
        return

    helmsman = getattr(context.scene, "charon_helmsman", None)
    if helmsman is not None:
        helmsman.steal_slot_from_other_rows(self, picked)


class BatchShipReviewItem(bpy.types.PropertyGroup):
    """One row of the batch ship review list - see Helmsman.refresh_batch_ship_reviews.

    A scene level collection rather than reading the batch file straight
    into the panel's draw(), the same restriction that rules out doing that
    for the priority group list - see Optimiser.refresh_priority_part_list.
    Filled in by ImportBatch.execute() instead, once per Import Batch click.
    """

    ship_id: bpy.props.StringProperty()
    ship_name: bpy.props.StringProperty()
    part_count: IntProperty()
    slot: EnumProperty(items=get_slot_enum_items, name="Slot", update=_on_slot_changed)
    # Plain-string mirror of slot, kept in sync by _on_slot_changed and
    # everywhere else slot is assigned directly (assign_slots,
    # steal_slot_from_other_rows). get_slot_enum_items reads this instead of
    # slot itself, because slot is this same dynamic enum on every row and
    # resolving another row's slot from inside this callback would re-enter
    # it and recurse forever.
    slot_value: bpy.props.StringProperty()
    review_status: EnumProperty(
        items=REVIEW_STATUS_ITEMS, name="Review Status", default="PENDING"
    )
    # Whether this row is included at all - unchecked keeps the row visible
    # but takes it out of export and review, without deleting it from the
    # batch like Reject would. Defaults on so a fresh import exports as
    # before unless the user opts a ship out.
    included: BoolProperty(default=True)

    # Set for one redraw when another row just stole this row's slot, so the
    # panel can flag the box it happened to - see
    # Helmsman.steal_slot_from_other_rows and _on_slot_changed.
    slot_bumped: BoolProperty(default=False)


def _reassign_slots():
    """Timer callback - redo the slot assignments after a redraw.

    Registered by Helmsman.request_slot_reassign_if_save_changed, which
    cannot do the write itself. Returns None so the timer does not repeat.
    """
    scene = getattr(bpy.context, "scene", None)
    helmsman = getattr(scene, "charon_helmsman", None) if scene else None
    if helmsman is not None and len(helmsman.batch_ship_reviews):
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

    # Whether the batch ship list is showing - toggled by ImportBatch.
    batch_list_visible: BoolProperty(default=False)

    # Rows for the batch ship review list - filled in by ImportBatch.execute,
    # see BatchShipReviewItem.
    batch_ship_reviews: CollectionProperty(type=BatchShipReviewItem)

    # Which save slot the rows' corvette assignments were worked out against,
    # so a change of save slot can be noticed and the assignments redone -
    # see reassign_slots_if_save_changed.
    assigned_save_slot: bpy.props.StringProperty()

    # Which page of the batch list is showing - see get_page_count/set_page.
    # A batch longer than the save has corvettes for is split into pages of
    # corvette-count ships each, so every page can fill every slot.
    current_page: IntProperty(default=0, min=0)

    def toggle_active(self):
        self.is_active = not self.is_active
        return self.is_active

    def steer(self):
        self.steer_count += 1
        return self.steer_count

    def refresh_batch_ship_reviews(self):
        """Rebuild the review rows, one per ship in the batch file."""
        from ..utils import helmsman_utils

        self.batch_ship_reviews.clear()
        self.current_page = 0

        for ship in helmsman_utils.get_batch_ships():
            item = self.batch_ship_reviews.add()
            item.ship_id = ship["id"]
            item.ship_name = ship["name"]
            item.part_count = ship["part_count"]

        self.assign_slots()

    def get_page_size(self):
        """How many ships one page holds - one per corvette in the save.

        0 (no save picked, or no corvettes) means there is nothing to page
        against, so callers treat that as a single page holding everything.
        """
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
        """Switch to a page, clamped to what exists, and refill its slots."""
        page_count = self.get_page_count()
        self.current_page = max(0, min(page, page_count - 1))
        self.assign_slots()

    def assign_slots(self):
        """Pair each row on the current page with a corvette from the save.

        Each page fills every slot from the start: the first ship on the
        page goes to the first corvette, the second to the second, and so
        on, so switching pages re-fills the same slot numbers for the next
        batch of ships to review - see get_page_items. The corvette list is
        already sorted by user_data (its position in the player's ship
        slots) over in the host addon.

        Rows outside the current page are left on NO_SLOT_ID - they are not
        being exported right now, so nothing should point at a corvette
        that is not theirs to overwrite yet.
        """
        from ..utils import base_builder_utils

        corvettes = base_builder_utils.get_save_corvettes()

        # slot_value is cleared alongside slot so the free/in-use split in
        # get_slot_enum_items is worked out against this new assignment
        # rather than the one it replaced
        for item in self.batch_ship_reviews:
            item.slot_value = NO_SLOT_ID
            item.slot = NO_SLOT_ID
            item.slot_bumped = False

        for page_index, (_, item) in enumerate(self.get_page_items()):
            if page_index < len(corvettes):
                slot_id = str(corvettes[page_index].user_data)
                item.slot_value = slot_id
                item.slot = slot_id

        save_data = base_builder_utils.get_save_data()
        self.assigned_save_slot = save_data.nms_save_slot if save_data else ""

    def steal_slot_from_other_rows(self, changed_item, slot):
        """Clear `slot` off every other row on the page that was holding it.

        Only one row can point at a given corvette at a time, so picking a
        slot that another row on the same page already has bumps that row
        to NO_SLOT_ID instead of leaving two rows silently pointed at the
        same ship slot - see _on_slot_changed. Flags the bumped row so the
        panel can call it out for one redraw.
        """
        for _, item in self.get_page_items():
            if item == changed_item:
                continue
            # slot_value, not slot: this runs inside slot's own update
            # callback, and reading another row's slot would re-enter
            # get_slot_enum_items - see BatchShipReviewItem.slot_value.
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
        """Redo the assignments when the save slot has been changed under us.

        Called from the panel's draw(), which cannot write to the collection
        itself, so the work is put on a timer that runs once the redraw is
        over - the same trick the asset browser uses for its own post-draw
        work. Safe to call on every redraw: it does nothing until the save
        slot actually differs from the one the rows were assigned against,
        and the timer is only ever registered once at a time.
        """
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
