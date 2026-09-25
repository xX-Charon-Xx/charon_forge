import numpy as np
from mathutils import Vector


def mesh_bounds(mesh):
    """(size, centre) of a mesh's vertices along its own axes."""
    coords = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)
    if not len(coords):
        return Vector((1.0, 1.0, 1.0)), Vector()
    low, high = coords.min(axis=0), coords.max(axis=0)
    return Vector(high - low), Vector((low + high) / 2)
