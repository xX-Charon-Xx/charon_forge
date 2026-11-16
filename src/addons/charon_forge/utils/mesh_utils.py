import bpy
import numpy as np
from mathutils import Vector


def import_model(path):
    """Import a .glb or .fbx part model; a glb object is set back to XYZ rotation."""
    objects_before = set(bpy.data.objects)
    if path.lower().endswith(".glb"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        bpy.ops.import_scene.fbx(filepath=path)
    for item in bpy.data.objects:
        if item not in objects_before:
            item.rotation_mode = "XYZ"


def mesh_bounds(mesh):
    """(size, centre) of a mesh's vertices along its own axes."""
    coords = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)
    if not len(coords):
        return Vector((1.0, 1.0, 1.0)), Vector()
    low, high = coords.min(axis=0), coords.max(axis=0)
    return Vector(high - low), Vector((low + high) / 2)
