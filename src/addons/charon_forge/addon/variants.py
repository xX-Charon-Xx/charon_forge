"""The Variants panel: the active part's family, and swapping it for another
member in place."""

import bpy

from . import variants_operators, variants_presentation

classes = variants_operators.classes + variants_presentation.classes


def register():
    for _class in classes:
        bpy.utils.register_class(_class)


def unregister():
    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)
