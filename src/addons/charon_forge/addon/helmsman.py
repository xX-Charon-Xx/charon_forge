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
    """One entry per corvette in the selected save slot.

    Keyed by user_data, which is the corvette's position in the player's
    ship slots - see save_editor_utils.BaseData in the host addon, whose
    corvette list is already sorted by it.

    The "no slot" entry is always present, so a row the save has no corvette
    for has something valid to sit on. Blender drops an enum value that is
    not in this list, and without it such a row would silently fall back to
    the first corvette - the one failure mode worth avoiding here, since it
    would export a ship over a slot nobody chose.
    """
    global _slot_enum_items

    from ..utils import base_builder_utils

    _slot_enum_items = [
        (str(corvette.user_data), str(corvette.user_data), "")
        for corvette in base_builder_utils.get_save_corvettes()
    ]
    _slot_enum_items.append((NO_SLOT_ID, NO_SLOT_LABEL, "No ship slot in this save to write to"))
    return _slot_enum_items


# Approve/Pending/Reject as one enum instead of three separate buttons, so
# a row can only ever be in one of the three states - see
# BatchShipReviewItem.review_status.
REVIEW_STATUS_ITEMS = [
    ("APPROVE", "", "Approve this ship", "CHECKMARK", 0),
    ("PENDING", "", "Leave this ship pending", "SORTTIME", 1),
    ("REJECT", "", "Reject this ship", "X", 2),
]


class BatchShipReviewItem(bpy.types.PropertyGroup):
    """One row of the batch ship review list - see Helmsman.refresh_batch_ship_reviews.

    A scene level collection rather than reading the batch file straight
    into the panel's draw(), the same restriction that rules out doing that
    for the priority group list - see Optimiser.refresh_priority_part_list.
    Filled in by ImportBatch.execute() instead, once per Import Batch click.
    """

    ship_name: bpy.props.StringProperty()
    part_count: IntProperty()
    slot: EnumProperty(items=get_slot_enum_items, name="Slot")
    review_status: EnumProperty(
        items=REVIEW_STATUS_ITEMS, name="Review Status", default="PENDING"
    )


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

        for ship in helmsman_utils.get_batch_ships():
            item = self.batch_ship_reviews.add()
            item.ship_name = ship["name"]
            item.part_count = ship["part_count"]

        self.assign_slots()

    def assign_slots(self):
        """Pair each row with a corvette from the selected save slot.

        The first ship goes to the first corvette, the second to the second,
        and so on, so a whole batch can be exported in one go rather than
        picking a slot per row by hand. The corvette list is already sorted
        by user_data (its position in the player's ship slots) over in the
        host addon.

        A batch can be longer than the save has corvettes. Those extra rows
        are still listed - they are ships the user loaded and should see -
        but are left on NO_SLOT_ID rather than pointed at a corvette that
        is not theirs to overwrite.
        """
        from ..utils import base_builder_utils

        corvettes = base_builder_utils.get_save_corvettes()
        for index, item in enumerate(self.batch_ship_reviews):
            if index < len(corvettes):
                item.slot = str(corvettes[index].user_data)
            else:
                item.slot = NO_SLOT_ID

        save_data = base_builder_utils.get_save_data()
        self.assigned_save_slot = save_data.nms_save_slot if save_data else ""

    def get_unassigned_count(self):
        """How many rows the save has no corvette for."""
        return sum(1 for item in self.batch_ship_reviews if item.slot == NO_SLOT_ID)

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
