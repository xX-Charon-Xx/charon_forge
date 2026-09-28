"""Common scene tasks - the part of the base builder addon's
utils/blend_utils.py that Charon Forge calls."""

import math

import bmesh
import bpy


def ShowMessageBox(message="", title="Message Box", icon="INFO"):
    """Show a message in a popup, or print it when there is no window."""
    # popups crash blender when there is no window, e.g. in background mode
    window_manager = bpy.context.window_manager
    if bpy.app.background or window_manager is None or not window_manager.windows:
        print(f"{title}: {message}")
        return

    def draw(self, context):
        self.layout.label(text=message)

    window_manager.popup_menu(draw, title=title, icon=icon)


def add_to_scene(item, collection_name="Collection"):
    """Link an item into `collection_name` (made if missing), and out of every
    other collection it is in."""
    if collection_name not in bpy.data.collections:
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)

    collection = bpy.data.collections[collection_name]
    if item.name not in collection.objects:
        collection.objects.link(item)

    # operators like the fbx importer also link to the active collection
    for other_collection in list(item.users_collection):
        if other_collection != collection:
            other_collection.objects.unlink(item)


def get_item_by_name(item_name):
    return bpy.data.objects[item_name]


def item_exists_by_name(item_name):
    return item_name in bpy.data.objects


def remove_object(name):
    objs = bpy.data.objects
    if name in objs:
        objs.remove(objs[name], do_unlink=True)


def scene_refresh():
    """Force the dependency graph to update, so matrices are current."""
    bpy.context.view_layer.update()


def set_active_item(item):
    bpy.context.view_layer.objects.active = item


def select(selection, add=False):
    """Select an object or a list of them, alone unless `add`; the last one
    becomes active."""
    if not add:
        deselect_all()
        set_active_item(None)

    if not isinstance(selection, list):
        selection = [selection]

    for item in selection:
        item.select_set(True)

    set_active_item(selection[-1])


def get_current_selection():
    selected_objects = [o for o in bpy.context.scene.objects if o.select_get()]
    if selected_objects:
        return selected_objects[-1]


def get_distance_between(matrix1, matrix2):
    translate1 = matrix1.decompose()[0]
    translate2 = matrix2.decompose()[0]
    return math.sqrt(
        (translate2.x - translate1.x) ** 2
        + (translate2.y - translate1.y) ** 2
        + (translate2.z - translate1.z) ** 2
    )


def deselect_all():
    """Clear the selection without going through bpy.ops."""
    view_layer = bpy.context.view_layer
    for item in view_layer.objects:
        if item.select_get(view_layer=view_layer):
            item.select_set(False, view_layer=view_layer)


def select_only(item):
    deselect_all()
    view_layer = bpy.context.view_layer
    if item.name in view_layer.objects:
        item.select_set(True)
        view_layer.objects.active = item


# Merging ---
# above this many vertices the join operator is faster than bmesh
BMESH_MERGE_VERT_LIMIT = 110000


def needs_operator_join(objects):
    # vertex groups, shape keys and object linked materials are dropped by a bmesh merge
    for obj in objects:
        if obj.vertex_groups or obj.data.shape_keys:
            return True
        for slot in obj.material_slots:
            if slot.link != "DATA":
                return True
    return False


def merge_objects_with_bmesh(objects, object_name):
    """Join meshes into the first object's space, without bpy.ops."""
    base = objects[0]
    base_inverse = base.matrix_world.inverted()

    # slots are pooled by material across every object, in first seen order
    materials = []
    material_indices = {}

    bm = bmesh.new()
    for obj in objects:
        slot_map = []
        for slot in obj.material_slots:
            material = slot.material
            if material is None:
                slot_map.append(0)
                continue
            index = material_indices.get(material.name)
            if index is None:
                index = len(materials)
                material_indices[material.name] = index
                materials.append(material)
            slot_map.append(index)

        needs_remap = slot_map != list(range(len(slot_map)))

        if obj is base and not needs_remap:
            bm.from_mesh(obj.data)
            continue

        # Mesh.transform also carries custom split normals, a vertex loop would not
        mesh_copy = obj.data.copy()
        if obj is not base:
            mesh_copy.transform(base_inverse @ obj.matrix_world)

        if needs_remap:
            last_slot = len(slot_map) - 1
            indices = [0] * len(mesh_copy.polygons)
            mesh_copy.polygons.foreach_get("material_index", indices)
            mesh_copy.polygons.foreach_set(
                "material_index",
                [slot_map[i if i <= last_slot else last_slot] for i in indices],
            )

        bm.from_mesh(mesh_copy)
        bpy.data.meshes.remove(mesh_copy)

    mesh = bpy.data.meshes.new(object_name)
    bm.to_mesh(mesh)
    bm.free()

    for material in materials:
        mesh.materials.append(material)

    merged = bpy.data.objects.new(object_name, mesh)
    for collection in base.users_collection:
        collection.objects.link(merged)
    merged.matrix_world = base.matrix_world.copy()
    return merged


def merge_objects_with_operator(objects, object_name):
    view_layer = bpy.context.view_layer
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    view_layer.objects.active = objects[0]

    # duplicate leaves its copy of the active object active, which is what gets joined into
    meshes_before = set(bpy.data.meshes)
    bpy.ops.object.duplicate(linked=False)

    # join writes into the active object's mesh in place. Parts share their
    # library's cached mesh, and duplicate can leave the copy on it (the
    # Duplicate Data preferences, library meshes) - joined into, every other
    # user of it would show the merge too: a forged text, whose hidden holder
    # object is over that mesh, turned into the QR code being grouped
    active = view_layer.objects.active
    if active.data.users > 1:
        active.data = active.data.copy()

    bpy.ops.object.join()

    merged = view_layer.objects.active
    merged.name = object_name

    # join keeps only the active mesh, the other duplicated meshes are left unused
    orphans = [
        mesh for mesh in bpy.data.meshes
        if mesh.users == 0 and mesh not in meshes_before
    ]
    if orphans:
        bpy.data.batch_remove(orphans)

    for key in list(merged.keys()):
        del merged[key]

    return merged


def merge_objects(objects, object_name):
    """Merge mesh objects into a new object, leaving the originals untouched.

    Returns:
        bpy.types.Object | None
    """
    objects = [obj for obj in objects if obj and obj.type == "MESH"]
    if not objects:
        print("No objects to merge")
        return None

    try:
        total_verts = sum(len(obj.data.vertices) for obj in objects)
        if needs_operator_join(objects) or total_verts > BMESH_MERGE_VERT_LIMIT:
            merged = merge_objects_with_operator(objects, object_name)
        else:
            merged = merge_objects_with_bmesh(objects, object_name)

        merged.data.update()
        select_only(merged)
        return merged

    except Exception as error:
        print("Error Occured while grouping objects : ", str(error))
        return None
