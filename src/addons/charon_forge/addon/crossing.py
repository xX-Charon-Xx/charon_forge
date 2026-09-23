import bpy
from bpy.props import BoolProperty, IntProperty, PointerProperty

from . import crossing_operators, crossing_presentation


# State for the crossing panel, stored on the scene as scene.charon_crossing.
class Crossing(bpy.types.PropertyGroup):

    # Dummy for now - nothing acts on it yet.
    is_active: BoolProperty(
        name="Crossing Active",
        description="Whether the crossing is currently active",
        default=False,
    )

    # dummy value, counts how many times the cross button was pressed
    cross_count: IntProperty(
        name="Cross Count",
        default=0,
        min=0,
    )

    def toggle_active(self):
        self.is_active = not self.is_active
        return self.is_active

    def cross(self):
        self.cross_count += 1
        return self.cross_count


classes = (
    Crossing,
) + crossing_operators.classes + crossing_presentation.classes


def register():
    for _class in classes:
        bpy.utils.register_class(_class)
    bpy.types.Scene.charon_crossing = PointerProperty(type=Crossing)


def unregister():
    del bpy.types.Scene.charon_crossing
    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)
