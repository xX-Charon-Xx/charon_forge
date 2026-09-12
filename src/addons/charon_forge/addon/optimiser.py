import bpy
from bpy.props import BoolProperty, IntProperty

from ..utils import dictionary


# State for the optimiser panel, stored on the scene as scene.charon_optimiser.
class Optimiser(bpy.types.PropertyGroup):

    # Dummy for now - nothing acts on it yet. Kept on the scene rather than
    # in preferences because whether a given base auto optimises is a
    # property of that file, not of the user.
    auto_optimise: BoolProperty(
        name="Auto Optimise",
        description="Optimise automatically as parts are placed",
        default=False,
    )

    # how many times materials.optimise_materials() has been run this session
    optimise_count: IntProperty(
        name="Optimise Count",
        default=0,
        min=0,
    )

    def optimise(self):
        self.optimise_count += 1
        return self.optimise_count

    # The priority list itself is not mirrored onto the scene - the panel
    # reads it straight off disk through dictionary.get_cached_priority_list.
    # A scene collection needed filling in from outside the draw pass, which
    # is what kept the old UIList version showing an empty list.
    def move_priority_group(self, index, direction):
        """Swap the group at index with its neighbour, then save."""
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

    def delete_priority_group(self, index):
        """Remove the group at index, then save."""
        priority_list = dictionary.get_priority_list()
        if index < 0 or index >= len(priority_list):
            return

        del priority_list[index]
        dictionary.save_priority_list(priority_list)

    def reset_priority_list(self):
        """Throw the user's edits away and go back to the shipped list."""
        dictionary.reset_priority_list()


classes = (
    Optimiser,
)
