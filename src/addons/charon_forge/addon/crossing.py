import json

import bpy
from bpy.props import BoolProperty, PointerProperty, StringProperty

from . import crossing_operators, crossing_presentation


# State for the crossing panel, stored on the scene as scene.charon_crossing.
class Crossing(bpy.types.PropertyGroup):

    # the last imported .nmsship's ship record and customisation, written back on export;
    # empty until an import, when export uses resources/nmsship_template.json
    ship_record_json: StringProperty()
    customisation_json: StringProperty()

    # the file the stored ship came from, for the panel to show
    source_file: StringProperty()

    # Export to Clipboard: just the parts, or the whole base around them
    clipboard_objects_only: BoolProperty(
        name="Objects Only",
        description=(
            "Copy only the list of parts. Off copies the whole base - its name, "
            "address and other properties - with the parts in it"
        ),
        default=True,
    )

    def store_ship(self, ship, customisation, source_file):
        self.ship_record_json = json.dumps(ship, ensure_ascii=False)
        self.customisation_json = json.dumps(customisation, ensure_ascii=False)
        self.source_file = source_file

    def get_ship(self):
        """(ship record, customisation) stored from an import, or None."""
        if not self.ship_record_json:
            return None
        try:
            return json.loads(self.ship_record_json), json.loads(self.customisation_json or "{}")
        except ValueError:
            return None

    def clear_ship(self):
        self.ship_record_json = ""
        self.customisation_json = ""
        self.source_file = ""


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
