import bpy
from bpy.props import CollectionProperty, IntProperty, StringProperty

from ..utils import dictionary


class PriorityListItem(bpy.types.PropertyGroup):
    """One row of the priority list UIList - a single priority group.

    order mirrors the group's position in priority_list.json (and so its
    index in the underlying array) rather than being stored independently,
    so it always reflects reality after a move/delete.
    """

    order: IntProperty(
        name="Order",
        description="Position of this group in the priority list",
    )
    summary: StringProperty(
        name="Parts",
        description="Object ids in this priority group",
    )


# State for the optimiser panel, stored on the scene as scene.charon_optimiser.
class Optimiser(bpy.types.PropertyGroup):

    # how many times materials.optimise_materials() has been run this session
    optimise_count: IntProperty(
        name="Optimise Count",
        default=0,
        min=0,
    )

    priority_list: CollectionProperty(type=PriorityListItem)
    priority_list_index: IntProperty()

    def optimise(self):
        self.optimise_count += 1
        return self.optimise_count

    def refresh_priority_list(self):
        """Rebuild the UIList rows from priority_list.json."""
        self.priority_list.clear()
        for group in dictionary.get_priority_list():
            item = self.priority_list.add()
            item.order = len(self.priority_list) - 1
            item.summary = ", ".join(group.values())

    def move_priority_group(self, index, direction):
        """Swap the group at index with its neighbour, then save and refresh."""
        priority_list = dictionary.get_priority_list()
        if index < 0 or index >= len(priority_list):
            return

        target = index + (-1 if direction == "UP" else 1)
        if target < 0 or target >= len(priority_list):
            return

        priority_list[index], priority_list[target] = (
            priority_list[target],
            priority_list[index],
        )
        dictionary.save_priority_list(priority_list)
        self.refresh_priority_list()
        self.priority_list_index = target

    def delete_priority_group(self, index):
        """Remove the group at index, then save and refresh."""
        priority_list = dictionary.get_priority_list()
        if index < 0 or index >= len(priority_list):
            return

        del priority_list[index]
        dictionary.save_priority_list(priority_list)
        self.refresh_priority_list()
        self.priority_list_index = min(index, len(priority_list) - 1)


classes = (
    PriorityListItem,
    Optimiser,
)
