import bpy
import os
import bmesh
import mathutils
import json
import math
import time
from mathutils import Matrix, Vector
import uuid

from .. import materials
from ..utils import mirror_utils, dictionary
from ..utils.base_builder_utils import blend_utils
from .part import Part

"""
    Manages grouping and ungrouping of NMS objects with safe caching.
    Handles relative matrix calculations, serialization, and restoration.
"""


def _charon_builder():
    """charon_forge.builder, imported on use rather than at module level.

    The builder imports this module, so importing it up top would be a cycle.
    """
    from .. import builder as charon_builder
    return charon_builder

class Group:
    
    # object properties
    PROP_OBJECT_ID = Part.PROP_OBJECT_ID
    PROP_USER_DATA = Part.PROP_USER_DATA
    PROP_TIMESTAMP = Part.PROP_TIMESTAMP
    PROP_MESSAGE = Part.PROP_MESSAGE
    
    # curve properties
    PROP_CHILD_CACHE = "child_cache"
    PROP_GROUP_ID = "GroupID"
    PROP_ORIGIN_OFFSET = "origin_offset"
    PROP_ORIGIN_MATRIX = "origin_matrix"
    PROP_PART_COUNT = "part_count"
    PROP_IS_MIRROR = "is_mirror"
    
    PROP_MATRIX_LOCAL = "matrix_local"

    def __init__(self):
        """Initialize the Groups manager."""
        pass


    @staticmethod
    def cache_relative_matrices( parent_obj, object_list ) :
        """
        Calculates the local matrices of objects relative to a parent, without
        actually changing their hierarchy.

        Args:
            parent_obj: The reference parent object
            object_list: List of objects to cache

        Returns:
            JSON-serialized string of cache data
        """
        cache_data = {}
        parent_matrix_inverted = parent_obj.matrix_world.inverted()

        for obj in object_list:
            if obj == parent_obj or Group.PROP_OBJECT_ID not in obj:
                continue

            matrix_local = parent_matrix_inverted @ obj.matrix_world
            matrix_list = [list(row) for row in matrix_local]

            cache = {
                Group.PROP_OBJECT_ID: obj[Group.PROP_OBJECT_ID],
                Group.PROP_USER_DATA: obj.get(Group.PROP_USER_DATA, 0),
                Group.PROP_TIMESTAMP: obj.get(Group.PROP_TIMESTAMP, int(time.time())),
                Group.PROP_MATRIX_LOCAL: matrix_list,
            }
            # a fossil bone's ObjectID is only its kind (FOS_SKULL); which
            # bone it is lives in its Message, which a rebuild needs to put
            # the right model back
            message = obj.get(Group.PROP_MESSAGE)
            if message:
                cache[Group.PROP_MESSAGE] = str(message)

            cache_data[obj.name] = cache

        return json.dumps(cache_data)
        

    @staticmethod
    def extract_cached_data(parent_obj) :
        """
        Reads the custom property cache from parent_obj and returns a dictionary
        mapping child names to cached data.

        Args:
            parent_obj: The parent object containing the cache

        Returns:
            Dictionary of cached child data, or None if not found or invalid
        """
        # a Forge sphere or shape writes its cache from its copies when read
        forged = getattr(parent_obj, "charon_forged", None)
        if forged is not None and forged.form:
            from .forged import Forged
            Forged.refresh_child_cache(parent_obj)

        if Group.PROP_CHILD_CACHE not in parent_obj:
            return None, None

        try:
            cache_child_data = json.loads(parent_obj[Group.PROP_CHILD_CACHE])
            origin_matrix_str = parent_obj.get(Group.PROP_ORIGIN_MATRIX)
            origin_matrix = Group.str_to_matrix(origin_matrix_str) if origin_matrix_str else None
            return cache_child_data, origin_matrix
        except (json.JSONDecodeError, Exception):
            return None, None


    @staticmethod
    def group_objects(objects_to_group, target_matrix=None):
        """
        Groups multiple objects into a single merged object.
        Applies the location and local rotation axes from the provided target_matrix.

        Args:
            objects_list (list[bpy.types.Object]): A list of Blender objects to be grouped.
            target_matrix (mathutils.Matrix, optional): A 4x4 transformation matrix defining the 
                origin location and local rotation axes for the new grouped object. 
                If None, the median position of all objects is used with a default global rotation.

        Returns:
            bpy.types.Object | None: Lis of objects if sucessful or None
        """
        if objects_to_group is None or len(objects_to_group) == 0:
            return None

        objects_list = []
        # Check if any object already has a GroupID
        for obj in objects_to_group:
            if Group.PROP_GROUP_ID in obj:
                return None
            if "ObjectID" in obj:
                objects_list.append(obj)

        # Keep location, rotation, and scale from the target matrix
        if target_matrix is not None:
            clean_matrix = target_matrix.copy()
        else:
            # Fallback: Calculate median position if no matrix is given
            clean_matrix = Matrix.Identity(4)
            total_location = Vector((0.0, 0.0, 0.0))
            for obj in objects_list:
                total_location += obj.matrix_world.translation
            clean_matrix.translation = total_location / len(objects_list)

        # read before the merge, which deletes nothing but strips the colour
        colour_info = Group.get_colour_info(objects_list)

        # Merge objects
        merged_object = blend_utils.merge_objects(objects_list, "Grouped_Objects")

        # this check used to sit after the write below, so a failed merge threw
        # a TypeError on None instead of returning None the way it says it does
        if merged_object is None:
            return None

        target_matrix_cache = json.dumps([list(row) for row in target_matrix]) if target_matrix is not None else None
        merged_object[Group.PROP_ORIGIN_MATRIX] = target_matrix_cache

        prev_position = merged_object.matrix_world.translation.copy()

        # Transform vertices so they do not visually move when we apply the new matrix.
        # Mesh.transform rather than a python loop over the vertices: it is the
        # difference between 30 ms and 1 ms on a small group, and it also carries
        # the custom split normals round with the geometry, which the loop left
        # pointing the old way.
        current_matrix = merged_object.matrix_world.copy()
        transform_matrix = clean_matrix.inverted() @ current_matrix

        merged_object.data.transform(transform_matrix)

        # Apply the clean matrix (this sets the new location and local axes)
        merged_object.matrix_world = clean_matrix
        merged_object.data.update()

        # Calculate origin difference for the cache
        new_location = merged_object.matrix_world.translation.copy()
        origin_difference = prev_position - new_location

        # Convert difference to local space and store
        local_difference = merged_object.matrix_world.to_3x3().inverted() @ origin_difference
        merged_object[Group.PROP_ORIGIN_OFFSET] = local_difference

        # Cache all combined objects
        child_cache = Group.cache_relative_matrices(merged_object, objects_list)
        #child_cache[Group.PROP_ORIGIN_MATRIX] = target_matrix_cache
        number_of_objects_grouped = len(objects_list)
        merged_object[Group.PROP_CHILD_CACHE] = child_cache
        merged_object[Group.PROP_GROUP_ID] = str(uuid.uuid4())
        merged_object[Group.PROP_PART_COUNT] = number_of_objects_grouped
        merged_object[Group.PROP_IS_MIRROR] = False

        Group.carry_colour(merged_object, colour_info)

        # Delete original objects - in one batch, because a remove() per object
        # re-syncs the whole scene each time and costs about 4 ms a piece on a
        # big base
        bpy.data.batch_remove([obj for obj in objects_to_group if obj is not None])

        return merged_object

    @staticmethod
    def get_colour_info(objects_list):
        """What carry_colour needs to know about the parts, read before they
        are merged: (the colour the group shows, a high res part id), either
        None when no part is high res."""
        user_data = Group.get_representative_user_data(objects_list)
        high_res_id = next(
            (materials.object_id_of(obj) for obj in objects_list if materials.is_high_res(obj)),
            None,
        )
        return user_data, high_res_id

    @staticmethod
    def carry_colour(merged_object, colour_info):
        """Put the parts' look back onto the object they were merged into.

        A merge strips every custom property off the merged object, and an
        absent palette slot reads as black in the colourise node group, so a
        group of high res parts came out with all of its paintable regions
        blacked out until it was ungrouped again.

        The mesh is tagged high res too. One merge path kept the first
        part's tag and the other lost it, and without it colouring the group
        painted a flat material over every slot instead of recolouring it.
        """
        user_data, high_res_id = colour_info
        mesh = merged_object.data
        if high_res_id and mesh is not None and materials.MESH_TAG not in mesh:
            mesh[materials.MESH_TAG] = high_res_id

        if user_data is not None:
            # Only the palette properties, never UserData - ungroup treats a
            # UserData on the group as a master colour to force onto every
            # child, and that should only happen when the user has actually
            # recoloured the group, not just because they grouped it.
            materials.apply(merged_object, user_data)

    @staticmethod
    def repair_scene_colours():
        """Give back their colour to groups that lost it to a merge.

        Groups made before carry_colour existed - by the base builder addon's
        Group button in particular - have high res materials but no palette,
        and show black until ungrouped. Their colour is still in their cache:
        the master colour if they were recoloured, else what most of their
        parts had.

        Returns:
            int: How many groups were repaired.
        """
        repaired = 0
        for obj in bpy.data.objects:
            if Group.PROP_GROUP_ID not in obj or obj.type != "MESH":
                continue
            if "nms_p" in obj or not materials.is_colourable(obj):
                continue

            children, _origin = Group.extract_cached_data(obj)
            children = children or {}
            user_data = obj.get(Group.PROP_USER_DATA)
            if user_data is None:
                counts = {}
                for cache_data in children.values():
                    value = cache_data.get(Group.PROP_USER_DATA)
                    if value is not None:
                        counts[str(value)] = counts.get(str(value), 0) + 1
                user_data = max(counts, key=counts.get) if counts else None
            high_res_id = next(
                (Group._model_id(cache_data) for cache_data in children.values()), None
            )

            Group.carry_colour(obj, (user_data, high_res_id))
            repaired += 1
        return repaired

    @staticmethod
    def get_representative_user_data(objects_list):
        """Pick the one colour a merged group should show.

        A group is a single object, and colour lives on the object, so it can
        only carry one. The most common colour among the parts is the closest
        match to what was just grouped - a wall of ten white panels with one red
        door should read as white. Ties go to whichever was seen first.

        Only high res parts get a vote. The old proxies keep their colour in
        their material, which survives the merge on its own.

        Args:
            objects_list (list): The objects being grouped.

        Returns:
            The UserData value to show, or None if nothing needs one.
        """
        counts = {}
        for obj in objects_list:
            if not materials.is_high_res(obj):
                continue
            user_data = obj.get(Part.PROP_USER_DATA)
            if user_data is None:
                continue
            user_data = str(user_data)
            counts[user_data] = counts.get(user_data, 0) + 1

        if not counts:
            return None
        return max(counts, key=counts.get)

    @staticmethod
    def ungroup_objects( builder, parent_obj):
        """
        Restores grouped objects back to their original state from cache.

        Args:
            builder: The builder instance (with add_part method)
            parent_obj: The grouped parent object to ungroup

        Returns:
            List of restored objects, or None if operation fails
        """
        cached_child_data, origin_matrix = Group.extract_cached_data(parent_obj)
        if not cached_child_data:
            return None
        
        master_user_data = parent_obj.get("UserData",None)
        
        restored_objects = []

        for child_name, cache_data in cached_child_data.items():

            object_id = cache_data[Group.PROP_OBJECT_ID]
            if master_user_data is not None:
                user_data = master_user_data 
            else:
                user_data = cache_data.get(Group.PROP_USER_DATA, 0) 
            time_stamp = cache_data.get(Group.PROP_TIMESTAMP, int(time.time()))

            # Add part via builder - the caller's builder is passed through so
            # its part cache stays the one that gets filled
            new_part = _charon_builder().add_part(
                Group._model_id(cache_data), user_data,
                builder_object=builder
            )
            if new_part is None or not hasattr(new_part, "object"):
                continue

            new_obj = new_part.object

            # Restore properties
            new_obj[Group.PROP_TIMESTAMP] = time_stamp
            if Group.PROP_MESSAGE in cache_data:
                new_obj[Group.PROP_MESSAGE] = cache_data[Group.PROP_MESSAGE]

            # Restore transform
            matrix_local_data = cache_data.get("matrix_local")
            if not matrix_local_data:
                continue

            new_obj.matrix_world = Group.restore_matrix_world(parent_obj, cache_data)
            restored_objects.append(new_obj)

        # Delete parent object
        bpy.data.objects.remove(parent_obj, do_unlink=True)
        return restored_objects


    @staticmethod
    def serialise(parent_obj):
        """
        Converts grouped objects to serialized format for No Man's Sky savefile.

        Args:
            parent_obj: The group_object object to serialize, these obejcts have "GroupID" property attached to them

        Returns:
            List of serialized object dictionaries, or None if operation fails
        """
        cached_child_data, origin_matrix = Group.extract_cached_data(parent_obj)
        if not cached_child_data:
            return None
        
        master_user_data = parent_obj.get("UserData",None)

        serialized_objects = []
        for child_name, cache_data in cached_child_data.items():

            object_id = cache_data[Group.PROP_OBJECT_ID]
            if master_user_data is not None:
                user_data = master_user_data 
            else:
                user_data = cache_data.get(Group.PROP_USER_DATA, 0) 
            time_stamp = cache_data.get(Group.PROP_TIMESTAMP, int(time.time()))
            message = cache_data.get(Group.PROP_MESSAGE)

            # Build world matrix
            matrix_world = Group.restore_matrix_world(parent_obj, cache_data)
            if matrix_world is None:
                continue
            
            pos, up, at = Group.extract_pos_up_at(matrix_world)
            
            data = {
                Part.PROP_TIMESTAMP: int(time_stamp),
                Part.PROP_OBJECT_ID: f"^{object_id}",
                Part.PROP_USER_DATA: int(user_data),
                Part.PROP_POSITION: [pos[0], pos[1], pos[2]],
                Part.PROP_UP: [up[0], up[1], up[2]],
                Part.PROP_AT: [at[0], at[1], at[2]],
            }

            if message is not None:
                data[Part.PROP_MESSAGE] = message

            serialized_objects.append(data)

        return serialized_objects
    
    @staticmethod
    def deserialise_to_group(builder,child_cache, origin_matrix = None):
        """
        Deserialise string to group
        Args:
            builder: The builder instance (with add_part method)
            child_cache: string containing data related to grouped object
        Returns:
            merged_group: object that is a merged group
        """
        
        if origin_matrix is None:
            origin_matrix = Group.get_default_origin_matrix()
        
        try:
            cached_child_data = json.loads(child_cache)
        except (json.JSONDecodeError, Exception) as error:
            print("Error deserialise_to_group ", error)
            return None
        
        restored_objects = []
        for child_name, cache_data in cached_child_data.items():

            object_id = cache_data[Group.PROP_OBJECT_ID]
            user_data = cache_data.get(Group.PROP_USER_DATA, 0)
            time_stamp = cache_data.get(Group.PROP_TIMESTAMP, int(time.time()))

            # Add part via builder - the caller's builder is passed through so
            # its part cache stays the one that gets filled
            new_part = _charon_builder().add_part(
                Group._model_id(cache_data), user_data,
                builder_object=builder
            )
            if new_part is None or not hasattr(new_part, "object"):
                continue

            new_obj = new_part.object

            # Restore properties
            new_obj[Group.PROP_TIMESTAMP] = time_stamp
            if Group.PROP_MESSAGE in cache_data:
                new_obj[Group.PROP_MESSAGE] = cache_data[Group.PROP_MESSAGE]

            # Restore transform
            matrix_local_data = cache_data.get("matrix_local")
            if not matrix_local_data:
                continue
            # multiply the current world matrix by the local matrix.
            matrix_local = mathutils.Matrix(matrix_local_data)
            new_obj.matrix_world = origin_matrix@ matrix_local
            restored_objects.append(new_obj)
        
        merged_group = Group.group_objects(restored_objects,origin_matrix)
        return merged_group
    
    @staticmethod
    def deserialise_to_objects(builder,child_cache, origin_matrix = None, overall_userdata = None):
        """
        Deserialise string to ungrouped obejcts
        Args:
            builder: The builder instance (with add_part method)
            child_cache: string containing data related to grouped object
        Returns:
            merged_group: list of ungrouped objects
        """
        
        if origin_matrix is None:
            origin_matrix = Group.get_default_origin_matrix()
        
        try:
            cached_child_data = json.loads(child_cache)
        except (json.JSONDecodeError, Exception) as error:
            print("Error deserialise_to_group ", error)
            return None 
        
        restored_objects = []
        for child_name, cache_data in cached_child_data.items():

            object_id = cache_data[Group.PROP_OBJECT_ID]
            user_data = cache_data.get(Group.PROP_USER_DATA, 0)
            time_stamp = cache_data.get(Group.PROP_TIMESTAMP, int(time.time()))

            # Add part via builder - the caller's builder is passed through so
            # its part cache stays the one that gets filled
            new_part = _charon_builder().add_part(
                Group._model_id(cache_data), user_data,
                builder_object=builder
            )
            if new_part is None or not hasattr(new_part, "object"):
                continue

            new_obj = new_part.object

            # Restore properties
            new_obj[Group.PROP_TIMESTAMP] = time_stamp
            if Group.PROP_MESSAGE in cache_data:
                new_obj[Group.PROP_MESSAGE] = cache_data[Group.PROP_MESSAGE]

            # Restore transform
            matrix_local_data = cache_data.get("matrix_local")
            if not matrix_local_data:
                continue
            # multiply the current world matrix by the local matrix.
            matrix_local = mathutils.Matrix(matrix_local_data)
            new_obj.matrix_world = origin_matrix@ matrix_local
            restored_objects.append(new_obj)
            
        return restored_objects
    
    @staticmethod
    def restore_matrix_world(parent_obj, child_cache_data):
        matrix_local_data = child_cache_data.get("matrix_local")
        if not matrix_local_data:
            return None
        
        # multiply the parent's current world matrix by the local matrix.
        matrix_local = mathutils.Matrix(matrix_local_data)
        matrix_world = parent_obj.matrix_world @ matrix_local
        
        return matrix_world
    
    @staticmethod
    def extract_pos_up_at(matrix_world):
        # Bring the matrix from Blender Z-Up spoace into standard Y-up space.
        z_compensate = mathutils.Matrix.Rotation(math.radians(-90.0), 4, "X")
        world_matrix_offset = z_compensate @ matrix_world
        # Retrieve Position, Up and At vectors.
        pos = world_matrix_offset.decompose()[0]
        up = [
            world_matrix_offset[0][1],
            world_matrix_offset[1][1],
            world_matrix_offset[2][1],
        ]
        at = [
            world_matrix_offset[0][2],
            world_matrix_offset[1][2],
            world_matrix_offset[2][2],
        ]
        
        return pos, up, at
    
    @staticmethod
    def get_all_groups():
        """  Returns all groups presetin inside view_layer"""
        groups = []
        for obj in bpy.context.view_layer.objects:
            try:
                if obj is not None:
                    if Group.PROP_GROUP_ID in obj:
                        groups.append(obj)
            except ReferenceError:
                continue
        return groups
    
    @staticmethod
    def find_mirror_group(target, groups_list = None):
        """ 
        Return first group found in scene that is mirror of target object 
        Args:
            target: object who's mirror needs to be found,
            groups_list (optional) : list of groups in which search will take place, if None, all other groups will be used
        
        Returns:
            First mirror group found or None if no match was found
        """
        existing_groups = Group.get_all_groups() if groups_list is None else groups_list
        is_target_mirror = target.get(Group.PROP_IS_MIRROR, False)   
        
        for obj in existing_groups:
            try:
                # validate obj
                if obj is None or Group.PROP_GROUP_ID not in obj:
                    continue
                # check if target is not equal to obj
                if obj.name == target.name:
                    continue
                
                # check if their GroupIDs are equal
                if obj[Group.PROP_GROUP_ID] != target[Group.PROP_GROUP_ID]:
                    continue
                
                # Mirror of groups with same GroupIDs is needed so obj need to opposite "is_mirror" value than target object
                if obj[Group.PROP_IS_MIRROR] != is_target_mirror:
                    # return after all conditions are met because only first match is needed
                    return obj
            except ReferenceError:
                continue
        return None
    
    @staticmethod
    def extract_origin_matrix(group_obj):
        target_matrix_cache = group_obj[Group.PROP_ORIGIN_MATRIX]
        return Group.str_to_matrix(target_matrix_cache)
    
    @staticmethod
    def str_to_matrix(json_string):
        
        if not json_string:
            return None
        
        
        try:
            return Matrix(json.loads(json_string))
        except (json.JSONDecodeError, Exception):
            print("error deconding json string : ", json_string)
            return None
        
    @staticmethod
    def get_default_origin_matrix():
        return mathutils.Matrix.Identity(4)
    
    @staticmethod
    def mirror_cache_data(child_cache, origin_matrix, axis, center):
        """Mirror a group's cached children without building any of them.

        curve.mirror_curve used to deserialise the whole group into real
        objects, mirror those with the build tool, merge them back into a mesh
        and then delete the mesh - all to end up with two strings. Every step of
        that is matrix arithmetic on the cache, so this does the arithmetic.

        The maths is deliberately step for step what the long way round did:
        each child's world matrix is rebuilt from the origin, mirrored exactly
        as build_tool.mirror would mirror the object (same axis mapping, same
        per part corrections, keyed on the id before the swap), then expressed
        relative to the mirrored origin - which is what cache_relative_matrices
        would have recorded off the regrouped object.

        Args:
            child_cache (str): The group's serialised child cache.
            origin_matrix (mathutils.Matrix): The group's origin, or None.
            axis (str): Mirror axis, "X", "Y" or "Z".
            center: Centre of reflection.

        Returns:
            tuple: (new child cache json, new origin matrix) or (None, None).
        """
        try:
            cached_child_data = json.loads(child_cache)
        except (json.JSONDecodeError, Exception) as error:
            print("Error mirroring group cache: ", error)
            return None, None

        if origin_matrix is None:
            origin_matrix = Group.get_default_origin_matrix()

        new_origin = mirror_utils.mirror_matrix_world_universal(
            None, origin_matrix, axis, center
        )
        new_origin_inverted = new_origin.inverted()

        # build_tool.mirror is only ever handed X or Z for the parts themselves
        tool_axis = "Z" if axis == "Z" else "X"

        new_child_cache = {}
        for child_name, cache_data in cached_child_data.items():
            matrix_local_data = cache_data.get(Group.PROP_MATRIX_LOCAL)
            if not matrix_local_data:
                continue

            new_cache_data = dict(cache_data)
            object_id = cache_data[Group.PROP_OBJECT_ID]

            # a part whose mirrored twin is its own model gets swapped for it,
            # and that changes how the transform has to be corrected
            mirror_part_id = Part.get_mirror_part_id(object_id)
            mirror_part_exist = mirror_part_id in dictionary.get_nice_names_diictionary()

            matrix_world = origin_matrix @ mathutils.Matrix(matrix_local_data)
            # the correction is keyed on the id the part had going in, which is
            # what build_tool.mirror passes too
            matrix_world = mirror_utils.mirror_matrix_world_universal(
                object_id, matrix_world, tool_axis, center,
                mirror_part_exist=mirror_part_exist
            )
            matrix_local = new_origin_inverted @ matrix_world

            if mirror_part_exist:
                new_cache_data[Group.PROP_OBJECT_ID] = mirror_part_id
            new_cache_data[Group.PROP_MATRIX_LOCAL] = [
                list(row) for row in matrix_local
            ]
            new_child_cache[child_name] = new_cache_data

        # twins whose mesh isn't the part flipped the way the maths above
        # assumes - see builder/mirror_twins.py
        from ..builder import mirror_twins
        return mirror_twins.correct_mirrored_cache(cached_child_data, new_child_cache), new_origin

    @staticmethod
    def _model_id(cache_data):
        """Which model a cached child is built from: its ObjectID, or a
        fossil bone's Message - its ObjectID is only its kind (FOS_SKULL).
        Placed through add_part, a bone given its full id is split back into
        the kind and the Message by the base builder's bone class; merged, a
        bone the high res library lacks falls back to its own fbx model."""
        from ..builder import placement
        return placement.model_id_of(cache_data[Group.PROP_OBJECT_ID],
                                     cache_data.get(Group.PROP_MESSAGE))

    @staticmethod
    def _is_fossil(cache_data):
        return str(cache_data.get(Group.PROP_OBJECT_ID, "")).replace("^", "").startswith("FOS_")

    @staticmethod
    def _has_unknown_fossil(group_obj):
        """True if the group holds a fossil bone its cache can't say which
        bone it is - a group made before caches kept a fossil's Message.
        Rebuilding it would swap its bones for generic ones."""
        cached_child_data, _origin = Group.extract_cached_data(group_obj)
        return any(Group._is_fossil(child) and not child.get(Group.PROP_MESSAGE)
                   for child in (cached_child_data or {}).values())

    @staticmethod
    def _rebuild_group_mesh(group_obj, builder, target_high_res, proxy_cache=None):
        """Build the merged mesh a group would have at the other quality.

        The group's own object is never touched here - this only produces the
        mesh and the colour that go with it, so the caller can decide what to
        do with them.

        Args:
            group_obj (bpy.types.Object): The group whose cache to rebuild.
            builder: The builder instance, kept for the caller's cache.
            target_high_res (bool): True to rebuild with models-high-res parts,
                False for the old fbx proxies.
            proxy_cache (dict): Carried across a batch - see
                charon_builder.new_proxy_object.

        Returns:
            tuple: (mesh, representative UserData), or (None, None) when the
                group has no usable cache to rebuild from.
        """
        cached_child_data, origin_matrix = Group.extract_cached_data(group_obj)
        if not cached_child_data:
            return None, None
        if origin_matrix is None:
            origin_matrix = Group.get_default_origin_matrix()

        charon_builder = _charon_builder()
        restored_objects = []

        try:
            for cache_data in cached_child_data.values():
                matrix_local_data = cache_data.get(Group.PROP_MATRIX_LOCAL)
                if not matrix_local_data:
                    continue

                object_id = cache_data[Group.PROP_OBJECT_ID]
                user_data = cache_data.get(Group.PROP_USER_DATA, 0)

                # Deliberately not add_part(): every one of these is merged and
                # deleted a few lines below, so the part class, the rig, the
                # snapping metadata and the palette properties add_part sets up
                # are all thrown away before anything can read them. See
                # charon_builder.new_merge_source.
                new_obj = charon_builder.new_merge_source(
                    Group._model_id(cache_data),
                    user_data,
                    high_res=target_high_res,
                    proxy_cache=proxy_cache,
                )
                if new_obj is None:
                    continue
                new_obj[Group.PROP_OBJECT_ID] = object_id

                new_obj.matrix_world = origin_matrix @ mathutils.Matrix(matrix_local_data)
                restored_objects.append(new_obj)
        except Exception:
            # A half built group's children must not be left loose in the scene
            bpy.data.batch_remove(restored_objects)
            raise

        if not restored_objects:
            return None, None

        # blend_utils.merge_objects carries mesh level custom properties -
        # the high res marker included - across from whichever object is
        # first in the list. An id the target library doesn't cover falls
        # back to the other quality on its own (see new_merge_source), so
        # without this a group that is mostly high res but starts with one
        # fallback part would merge into a mesh that reads as low res.
        restored_objects.sort(
            key=lambda obj: materials.is_high_res(obj) != target_high_res
        )

        # Read off the children while they still exist. This used to be asked
        # for after the merge, and group_objects deletes every object it
        # merges, so any group without an explicit master colour of its own
        # raised a ReferenceError on the freed children instead of switching.
        representative_user_data = Group.get_representative_user_data(restored_objects)

        # group_objects only exists here to produce a merged mesh at the
        # origin - the scratch object it hands back is thrown away the moment
        # its mesh is lifted off, so group_obj's own identity never changes
        # hands.
        scratch_group = Group.group_objects(restored_objects, origin_matrix)
        if scratch_group is None:
            # It deletes what it merged and nothing else, so on any of its
            # failure paths the rebuilt children are still sitting in the
            # scene - a group's worth of loose parts, which is how a failed
            # switch used to look to the user.
            bpy.data.batch_remove(restored_objects)
            return None, None

        mesh = scratch_group.data
        bpy.data.objects.remove(scratch_group, do_unlink=True)
        return mesh, representative_user_data

    @staticmethod
    def _apply_switched_colour(group_obj, target_high_res, fallback_user_data):
        """Put the colour back on a group whose mesh has just been swapped.

        Colour lives on the object, not the mesh, so it survives the data swap
        untouched - but it was voted on by the OLD children and is now stale.
        An explicit master colour (set by recolouring the group after it was
        made) takes precedence, same as ungroup treats it; otherwise the one
        derived from the parts just rebuilt is used.

        Args:
            group_obj (bpy.types.Object): The group that was switched.
            target_high_res (bool): The quality it was switched to.
            fallback_user_data: The UserData derived from its children, or None.
        """
        if not target_high_res:
            materials.clear(group_obj)
            return

        user_data_value = group_obj.get(Part.PROP_USER_DATA)
        if user_data_value is None:
            user_data_value = fallback_user_data
        if user_data_value is not None:
            materials.apply(group_obj, user_data_value)

    @staticmethod
    def switch_proxy_quality(
        group_obj, builder, target_high_res,
        mesh_cache=None, proxy_cache=None, dead_meshes=None, force=False,
    ):
        """Rebuild one group's mesh at the requested proxy quality, in place.

        Every child in the group's cache is rebuilt at the new quality and
        re-merged, the same way deserialise_to_group turns a cache back into
        a group. Only group_obj's mesh data block is replaced - its name,
        transform, parent, collections, GroupID, mirror flag, origin and
        cache are never touched, so nothing else in the scene that refers to
        this object is disturbed by the switch.

        Args:
            group_obj (bpy.types.Object): The group to convert.
            builder: The builder instance passed through to the rebuild.
            target_high_res (bool): True to rebuild with models-high-res
                parts, False for the old fbx proxies.
            mesh_cache (dict): Optional {child cache: (mesh, UserData)} carried
                across a batch. A group's merged geometry is built in its
                children's local space and only then moved onto the group's
                origin, so it depends on the child cache alone and not on where
                the group sits - which means two groups with the same cache
                (Shift+D copies of one another, the usual way a prefab gets
                repeated) can share one rebuild and take a copy of the mesh
                each, instead of importing and merging every child twice.
            proxy_cache (dict): Optional, carried across a batch - see
                charon_builder.new_proxy_object.
            dead_meshes (list): Optional. The mesh being replaced is appended
                here instead of being removed, so a caller switching a whole
                scene can clear them all out at the end - see
                switch_scene_proxy_quality.
            force (bool): Rebuild it even if it is already at that quality -
                to pick up library parts that were reimported.

        Returns:
            bool: True if the object's mesh was switched.
        """
        if not force and materials.is_high_res(group_obj) == target_high_res:
            return False

        cache_key = group_obj.get(Group.PROP_CHILD_CACHE)
        cached = mesh_cache.get(cache_key) if mesh_cache is not None else None

        if cached is not None:
            new_data, user_data_value = cached
            # A copy rather than the datablock itself: sharing it would turn
            # two groups that merely look alike into linked duplicates, and
            # editing one would then change the other. Copying a mesh is cheap
            # next to rebuilding and re-merging every part in it.
            new_data = new_data.copy()
        else:
            new_data, user_data_value = Group._rebuild_group_mesh(
                group_obj, builder, target_high_res, proxy_cache=proxy_cache
            )
            if new_data is None:
                return False
            if mesh_cache is not None and cache_key is not None:
                mesh_cache[cache_key] = (new_data, user_data_value)

        old_data = group_obj.data
        group_obj.data = new_data
        if old_data is not None:
            if dead_meshes is not None:
                dead_meshes.append(old_data)
            elif old_data.users == 0:
                bpy.data.meshes.remove(old_data)

        Group._apply_switched_colour(group_obj, target_high_res, user_data_value)
        return True

    @staticmethod
    def switch_scene_proxy_quality(context, builder, target_high_res,
                                   proxy_cache=None, force=False):
        """Switch every group in the scene to the requested proxy quality.

        Linked duplicates - separate objects still sharing one mesh data
        block, the usual result of Alt+D - are only rebuilt once; every
        other object that shared the old block is pointed at the new one
        instead of getting its own independent copy, so the sharing survives
        the switch. A mirror group is unaffected by this - it already keeps
        its own reflected cache and its own data block, so it is rebuilt from
        that cache like any other group and comes out correctly mirrored on
        its own, whether or not its counterpart is switched in the same pass.

        Args:
            context: The context to read the scene's objects from.
            builder: The builder instance passed through to the rebuild.
            target_high_res (bool): True to rebuild with models-high-res
                parts, False for the old fbx proxies.
            proxy_cache (dict): Optional, carried across a batch - see
                charon_builder.apply_proxy_mesh. Worth passing the same one the
                caller used for the loose parts: a group child and a placed
                part of the same (ObjectID, UserData) want the same proxy mesh,
                and sharing the cache means the fbx behind it is imported and
                painted once for both.
            force (bool): Rebuild every group, even those already at that
                quality - see switch_proxy_quality.

        Returns:
            tuple: (groups switched, groups that could not be rebuilt).
        """
        rebuilt_data = {}
        mesh_cache = {}
        proxy_cache = {} if proxy_cache is None else proxy_cache
        dead_meshes = []
        switched = 0
        failed = 0

        # One library-wide dedupe and finish pass for the whole scene rather
        # than one per part rebuilt inside it.
        with materials.defer_shared_data():
            for group_obj in list(context.scene.objects):
                if Group.PROP_GROUP_ID not in group_obj:
                    continue
                # a Forge sphere's or shape's mesh is the points its node
                # tree places the part on, not a merged mesh - see
                # objects/forged.py
                forged = getattr(group_obj, "charon_forged", None)
                if forged is not None and forged.form:
                    continue
                if not force and materials.is_high_res(group_obj) == target_high_res:
                    continue
                # an unforced switch has no better choice, but a forced
                # refresh of an already high res group would only break it
                if force and Group._has_unknown_fossil(group_obj):
                    print("Charon Forge: left group %s as it is - it holds fossil "
                          "bones its cache doesn't name" % group_obj.name)
                    continue

                old_data = group_obj.data
                # Keyed by name, and nothing is actually removed until the loop
                # is over. A removed datablock left as a dict key raises the
                # moment the next lookup has to compare against it, and a name
                # freed mid loop can be handed straight back to one of the
                # meshes still being built.
                old_name = old_data.name if old_data is not None else None

                shared = rebuilt_data.get(old_name)
                if shared is not None:
                    shared_data, shared_user_data = shared
                    group_obj.data = shared_data
                    dead_meshes.append(old_data)
                    Group._apply_switched_colour(
                        group_obj, target_high_res, shared_user_data
                    )
                    switched += 1
                    continue

                cache_key = group_obj.get(Group.PROP_CHILD_CACHE)
                try:
                    was_switched = Group.switch_proxy_quality(
                        group_obj,
                        builder,
                        target_high_res,
                        mesh_cache=mesh_cache,
                        proxy_cache=proxy_cache,
                        dead_meshes=dead_meshes,
                        force=force,
                    )
                except Exception as error:
                    # One unrebuildable group must not take the rest of the
                    # scene down with it - a half switched scene with no idea
                    # which half is worse than a named failure.
                    print(
                        "Could not switch group %s: %s" % (group_obj.name, error)
                    )
                    failed += 1
                    continue

                if not was_switched:
                    failed += 1
                    continue

                if old_name is not None:
                    rebuilt_data[old_name] = (
                        group_obj.data,
                        mesh_cache.get(cache_key, (None, None))[1],
                    )
                switched += 1

        # Deferred to here on purpose - see the note on old_name above. Only
        # the ones nothing points at any more, and each of them once: a linked
        # duplicate puts the same block in the list as many times as it had
        # users.
        stale = {}
        for mesh in dead_meshes:
            if mesh is not None and mesh.users == 0:
                stale[mesh.name] = mesh
        if stale:
            bpy.data.batch_remove(list(stale.values()))

        return switched, failed

    @staticmethod
    def mirror_group_cache(group_obj, axis, center):
        """
        Directly mirrors the cached child data and origin matrix of a group object
        without needing to unpack and repack the geometry in the scene.
        """
        cached_child_data, origin_matrix = Group.extract_cached_data(group_obj)

        if cached_child_data is None:
            print("Error mirroring group cache: child cache is None")
            return None, None

        # This used to carry its own copy of the mirror maths, which was never
        # called and did not match what mirroring a group actually does. It now
        # goes through the one implementation that is checked against the long
        # build/mirror/regroup route.
        new_child_cache, new_origin_matrix = Group.mirror_cache_data(
            group_obj[Group.PROP_CHILD_CACHE], origin_matrix, axis, center
        )
        if new_child_cache is None:
            return None, None

        if new_origin_matrix is not None:
            group_obj[Group.PROP_ORIGIN_MATRIX] = json.dumps(
                [list(row) for row in new_origin_matrix]
            )
        group_obj[Group.PROP_CHILD_CACHE] = new_child_cache

        return json.loads(new_child_cache), new_origin_matrix
