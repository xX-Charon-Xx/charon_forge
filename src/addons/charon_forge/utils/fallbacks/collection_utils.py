"""Collection helpers - the base builder addon's utils/collection_utils.py,
for when it is not installed. Importing a base (importer.py) uses these."""

import bpy

LINKED_CURVE_OBJ_COL = "Linked Curve Objects"
UNLINKED_CURVE_OBJ_COL = "Unlinked Curve Objects"


def get_collection(collection_name):
    """The collection with this name, made and linked to the scene if missing."""
    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)
    return collection


def move_object_into_collection(collection, obj):
    """Link an object into `collection`, and out of every other one."""
    if collection not in obj.users_collection:
        collection.objects.link(obj)
    for other in list(obj.users_collection):
        if other != collection:
            other.objects.unlink(obj)


def move_collection_into_collection(parent_collection, child_collection):
    if child_collection not in parent_collection.children.values():
        parent_collection.children.link(child_collection)


def create_collection(collection_name, color_tag=None):
    collection = bpy.data.collections.new(collection_name)
    if color_tag is not None:
        collection.color_tag = color_tag
    return collection


def get_parent_collection(item):
    """The collection an object or collection sits in, or None."""
    if not item:
        return None

    if isinstance(item, bpy.types.Object):
        return item.users_collection[0] if item.users_collection else None

    if isinstance(item, bpy.types.Collection):
        scene_root = bpy.context.scene.collection
        if item in scene_root.children.values():
            return scene_root
        for potential_parent in bpy.data.collections:
            if item in potential_parent.children.values():
                return potential_parent
    return None
