"""Reading and writing No Man's Sky save files.

A copy of the base builder addon's save editor, so the Helmsman panel can
pick a save slot and write ships into it without that addon. Only the
SaveManager state is registered here (as scene.charon_save_data); the save
editor panel and operators are that addon's and are not registered.
"""

import bpy

from .save_manager import CharonSaveManager

classes = (CharonSaveManager,)


def register():
    for _class in classes:
        bpy.utils.register_class(_class)
    bpy.types.Scene.charon_save_data = bpy.props.PointerProperty(type=CharonSaveManager)


def unregister():
    del bpy.types.Scene.charon_save_data
    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)
