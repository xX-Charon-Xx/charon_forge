import json
import bpy
import math
from pathlib import Path

from mathutils import Matrix, Euler, Vector

MIRROR_CORRECTIONS_PATH = (
    Path(__file__).resolve().parents[1] / "resources" / "mirror_corrections.json"
)


def load_mirror_corrections():
    with open(MIRROR_CORRECTIONS_PATH, "r", encoding="utf-8") as stream:
        return json.load(stream)


MIRROR_CORRECTIONS = load_mirror_corrections()
LOCAL_Y_180_ROTATION_PARTS = set(MIRROR_CORRECTIONS["local_y_180_rotation_parts"])
LOCAL_Y_90_ROTATION_PARTS = set(MIRROR_CORRECTIONS["local_y_90_rotation_parts"])
MIRROR_Z_180_IDENTIFIERS = set(MIRROR_CORRECTIONS["mirror_z_180_identifiers"])
POSITION_OFFSETS = {
    part: Vector(offset)
    for part, offset in MIRROR_CORRECTIONS["position_offsets"].items()
}


def ShowMessageBox(message="", title="Message Box", icon="INFO"):
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


#This function mirrors matrix world across x axis
def mirror_matrix_world(object_id, old_matrix_world, across_x=True):

    #extract location,rotation and scale values from matrix world
    location, rotation_quaternion, scale = old_matrix_world.decompose()

    #mirror location  if across x is selected
    new_location = -location.x if across_x else location.x
    position_values = (new_location, location.y, location.z)
    position_matrix = Matrix.Translation(Vector(position_values))

    #mirror rotation across x axis
    current_euler = rotation_quaternion.to_euler("XYZ")
    rotation_values = (current_euler.x, -current_euler.y, -current_euler.z)
    rotation_euler = Euler(rotation_values, "XYZ")
    rotation_matrix = rotation_euler.to_matrix().to_4x4()

    #creating scale matrix
    scale_matrix = Matrix.Scale(scale.x, 4)

    #multiplying all the matrix
    matrix_world = position_matrix @ rotation_matrix @ scale_matrix

    #correct anomalies in mirroring
    matrix_world = mirror_correction(object_id, matrix_world)

    return matrix_world

def reflect_point_across(source,origin):
    return (2 * origin) - source


def reflect_point(source,origin, axis):
    """reflects a point across give asix assuming origin as center of reflection

    Args:
        source (Vector): location of point to be mirrored
        origin (Vector): center of reflection
        axis (String): ( Takes "X","Y","Z" ), direction in which to morror

    Returns:
        Vector: Location of mirrored point
    """
    if origin is None:
        return source
    
    x = reflect_point_across(source.x, origin.x) if axis == "X" else source.x
    y = reflect_point_across(source.y, origin.y) if axis == "Y" else source.y
    z = reflect_point_across(source.z, origin.z) if axis == "Z" else source.z
    return Vector((x,y,z))

# This function mirrors matrix world according to parameters passed
# Axis has three possible string values : X, Y and Z
# Center is a point across which mirroring will take place, it is a 3d Vector
def mirror_matrix_world_universal(object_id, old_matrix_world, axis = None, center = None, mirror_part_exist = False):

    #extract location,rotation and scale values from matrix world
    location, rotation_quaternion, scale = old_matrix_world.decompose()

    # mirror location according to axis
    position_vector = reflect_point(location,center,axis)
    position_matrix = Matrix.Translation(position_vector)

    # mirror rotation according to axis
    current_euler = rotation_quaternion.to_euler("XYZ")
    if axis == "X":
        rotation_values = (current_euler.x, -current_euler.y, -current_euler.z)
    elif axis == "Y":
        rotation_values = (current_euler.x, -current_euler.y, -current_euler.z + math.pi)
    else:# axis == "Z"
        rotation_values = (current_euler.x + math.pi, current_euler.y , current_euler.z + math.pi)
        
    rotation_euler = Euler(rotation_values, "XYZ")
    rotation_matrix = rotation_euler.to_matrix().to_4x4()

    #creating scale matrix
    scale_matrix = Matrix.Scale(scale.x, 4)

    #multiplying all the matrix
    matrix_world = position_matrix @ rotation_matrix @ scale_matrix
    
    #correct anomalies in mirroring
    if object_id is not None:
        matrix_world = mirror_correction(object_id, matrix_world)

    return matrix_world


def mirror_matrix_world_universal_2(object_id, old_matrix_world, axis=None, center=None, mirror_part_exist = False):
    if axis not in {"X", "Y", "Z"} or center is None:
        return old_matrix_world.copy()

    # Extract the basic transformation components
    location, rotation_quaternion, scale = old_matrix_world.decompose()
    
    flip_vector = Vector((
        -1.0 if axis == "X" else 1.0,
        -1.0 if axis == "Y" else 1.0,
        -1.0 if axis == "Z" else 1.0,
    ))
    
    rotation_matrix = rotation_quaternion.to_matrix()
    rotation_matrix.col[0] *= flip_vector       # local X
    rotation_matrix.col[1] *= flip_vector * -1  # local Y
    rotation_matrix.col[2] *= flip_vector       # local Z
    
    # Mirror Position based on the chosen global mirror plane
    location_vector = reflect_point(location, center, axis)

    # rotation matrix
    new_rotation_matrix = rotation_matrix.to_4x4()
    # translation matrix
    new_translation_matrix = Matrix.Translation(location_vector)
    # scale matrix
    new_scale_matrix = Matrix.Scale(scale.x, 4)
    
    rotation_correction = Matrix.Rotation(math.pi, 4, "Z" if mirror_part_exist else "X")
    # combined matrix
    matrix_world = new_translation_matrix @ new_rotation_matrix @ new_scale_matrix @ rotation_correction

    return matrix_world


# This function changes orientation of object my adding 180 degree to its rotation value
# This is useful when used on Corvette parts
def change_orientation(object_id, old_matrix_world, axis = None, has_mirror_part = False):
    #mirror rotation across x axis
    local_rotation = Matrix.Rotation(0, 4, "X")
    if axis == "X" and not has_mirror_part:
        local_rotation = Matrix.Rotation(math.pi, 4, "X")
    if axis == "Y":
        local_rotation = Matrix.Rotation(math.pi, 4, "Y")
    elif axis == "Z":
        local_rotation = Matrix.Rotation(math.pi, 4, "Z")

    return old_matrix_world @ local_rotation


#This function provides additional corrections after mirroring object
def mirror_correction(object_id, matrix_world):
    #All triangular floor tiles
    if any(identifier in object_id for identifier in MIRROR_Z_180_IDENTIFIERS):
        angle = math.pi  #180 degrees
        z_rot_180 = Matrix.Rotation(angle, 4, "Z")
        return matrix_world @ z_rot_180

    #Apply per-part position offset corrections
    if object_id in POSITION_OFFSETS:
        translation_matrix = Matrix.Translation(POSITION_OFFSETS[object_id])
        return matrix_world @ translation_matrix

    #Parts that need rotation by 180 on local Y axis
    if object_id in LOCAL_Y_180_ROTATION_PARTS:
        angle = math.pi  #180 degrees
        y_rot_180 = Matrix.Rotation(angle, 4, "Y")
        return matrix_world @ y_rot_180
    
    #Parts that need rotation by 90 on local Y axis
    if object_id in LOCAL_Y_90_ROTATION_PARTS:
        angle = math.pi/2  #90 degrees
        y_rot_90 = Matrix.Rotation(angle, 4, "Y")
        return matrix_world @ y_rot_90

    return matrix_world

