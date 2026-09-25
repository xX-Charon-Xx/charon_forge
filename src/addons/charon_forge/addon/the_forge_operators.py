import bpy

from ..builder import station_library
from ..objects.circle import Circle
from ..objects.cuboid import Cuboid
from ..objects.forged import Forged
from ..objects.group import Group
from ..objects.part import Part
from ..objects.polygon import Polygon
from ..objects.rectangle import Rectangle
from ..objects.shape import Shape
from ..objects.sphere import Sphere


def forge_source_problem(obj):
    """Why an object can't be forged into anything, or None if it can."""
    if obj is None:
        return "Select a part first"
    if obj.type != "MESH" or Part.PROP_OBJECT_ID not in obj or Group.PROP_GROUP_ID in obj:
        return "The selected object is not a part"
    if obj.children:
        return "Parts with attached pieces can't be forged"
    return None


def _select_only(context, objects):
    for obj in context.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    if objects:
        context.view_layer.objects.active = objects[0]


class _CreateForged:
    """Shared by the create operators - `kind` is what they make."""

    bl_options = {"REGISTER", "UNDO"}
    kind = None

    @classmethod
    def poll(cls, context):
        problem = forge_source_problem(context.active_object)
        if problem:
            cls.poll_message_set(problem)
            return False
        return True

    def execute(self, context):
        forged_obj = self.kind.create(context.active_object)
        _select_only(context, [forged_obj])
        message = forged_obj.charon_forged.message
        if message:
            self.report({"WARNING"}, message)
        return {"FINISHED"}


class CreateSphere(_CreateForged, bpy.types.Operator):
    """Turn the selected part into a sphere of copies of it, one object you can keep adjusting"""

    bl_idname = "object.charon_forge_create_sphere"
    bl_label = "Sphere"
    kind = Sphere


class CreateShape(_CreateForged, bpy.types.Operator):
    """Turn the selected part into a closed shape - pyramid, prism, any number of corners - built from copies of it"""

    bl_idname = "object.charon_forge_create_shape"
    bl_label = "Shape"
    kind = Shape


class CreateCuboid(_CreateForged, bpy.types.Operator):
    """Turn the selected part into a box of copies of it - any width, depth and height"""

    bl_idname = "object.charon_forge_create_cuboid"
    bl_label = "Cuboid"
    kind = Cuboid


class SplitForged(bpy.types.Operator):
    """Break it into its separate parts. It can't be adjusted after"""

    bl_idname = "object.charon_forge_split"
    bl_label = "Split into Parts"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return Forged.is_forged(context.active_object)

    def execute(self, context):
        from ..builder import get_builder

        parts = Forged.split(context.active_object, get_builder())
        _select_only(context, parts)
        self.report({"INFO"}, f"Split into {len(parts)} part(s)")
        return {"FINISHED"}


class ResetForged(bpy.types.Operator):
    """Put every setting back to how it started when this was made"""

    bl_idname = "object.charon_forge_reset"
    bl_label = "Reset"
    bl_options = {"REGISTER", "UNDO"}

    # what was measured off the part or is kept by the object itself, and
    # stays as it is
    KEPT = {
        "rna_type", "name", "form", "part_object", "object_id", "base_scale", "part_size",
        "pitch_around", "pitch_up", "base_rotation", "centre_offset", "applied_scale",
        "part_count", "message", "shape_info",
    }

    @classmethod
    def poll(cls, context):
        return Forged.is_forged(context.active_object)

    def execute(self, context):
        forged_obj = context.active_object
        settings = forged_obj.charon_forged
        with Forged.suspended():
            for prop in settings.bl_rna.properties:
                if prop.identifier not in self.KEPT and not prop.is_readonly:
                    settings.property_unset(prop.identifier)
            # the starting size each kind works out from the part
            Forged.kind_of(forged_obj).initialise(settings)
        Forged.update(forged_obj)
        return {"FINISHED"}


class EditStation(bpy.types.Operator):
    """Import a space station - its interior, its exterior or both - at the 3D cursor, or change the one in the scene"""

    bl_idname = "object.charon_forge_edit_station"
    bl_label = "Space Station"
    bl_options = {"REGISTER", "UNDO"}

    use_interior: bpy.props.BoolProperty(
        name="Interior", description="Have the station's interior - its core and runway",
        default=True,
    )
    interior: bpy.props.EnumProperty(
        name="Interior", description="Which space station interior",
        items=station_library.INTERIORS,
    )
    use_exterior: bpy.props.BoolProperty(
        name="Exterior", description="Have the station's exterior - its outer body",
        default=True,
    )
    exterior: bpy.props.EnumProperty(
        name="Exterior", description="Which space station exterior",
        items=station_library.EXTERIORS,
    )
    colours: bpy.props.EnumProperty(
        name="Colours", description="The station palette to colour it with",
        items=station_library.palette_items,
    )

    _PARTS = (
        (station_library.INTERIOR, "use_interior", "interior"),
        (station_library.EXTERIOR, "use_exterior", "exterior"),
    )

    def invoke(self, context, event):
        # start from the station that's there: its parts ticked, their kinds
        # and colours chosen
        stations = station_library.find_stations()
        if stations:
            for part, use, kind in self._PARTS:
                current = station_library.find_station(part)
                setattr(self, use, current is not None)
                if current is not None:
                    setattr(self, kind, current[station_library.PROP_KIND])
            try:
                self.colours = str(stations[0].get(station_library.PROP_PALETTE,
                                                   station_library.SAVED_PALETTE))
            except TypeError:
                pass
        verb = "Modify" if stations else "Import"
        return context.window_manager.invoke_props_dialog(
            self, title="%s Space Station" % verb, confirm_text=verb
        )

    def draw(self, context):
        layout = self.layout
        for part, use, kind in self._PARTS:
            row = layout.row(align=True)
            split = row.split(factor=0.35, align=True)
            split.prop(self, use)
            choice = split.row(align=True)
            choice.enabled = getattr(self, use)
            choice.prop(self, kind, text="")
        split = layout.split(factor=0.35, align=True)
        split.label(text="Colours")
        split.prop(self, "colours", text="")

    def execute(self, context):
        if not self.use_interior and not self.use_exterior and not station_library.find_stations():
            self.report({"WARNING"}, "Tick the interior, the exterior or both")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        palette = int(self.colours)
        imported, missing, done = [], 0, []
        for part, use, kind_name in self._PARTS:
            wanted = getattr(self, use)
            kind = getattr(self, kind_name)
            current = station_library.find_station(part)

            # the same kind only needs its colours changing - nothing reloads
            if wanted and current is not None and current[station_library.PROP_KIND] == kind:
                station_library.recolour(current, palette)
                done.append("recoloured the %s" % part.lower())
                continue
            # an unticked part, or one swapped for another kind, goes
            if current is not None:
                station_library.remove_station(current)
                if not wanted:
                    done.append("removed the %s" % part.lower())
            if not wanted:
                continue
            try:
                collection, objects, part_missing = station_library.import_part(
                    context, part, kind, palette
                )
            except FileNotFoundError as error:
                self.report({"ERROR"}, "Station %s not found: %s" % (part.lower(), error))
                return {"CANCELLED"}
            imported += objects
            missing += part_missing
            done.append("imported %s" % collection.name)

        if imported:
            station_library.extend_view_clip()
            _select_only(context, [obj for obj in imported if obj.visible_get()])
        summary = "; ".join(done).capitalize() or "Nothing to change"
        if missing:
            self.report({"WARNING"}, "%s - %d textures not found in "
                        "models/space_station/textures" % (summary, missing))
        else:
            self.report({"INFO"}, summary)
        return {"FINISHED"}


class RemoveStation(bpy.types.Operator):
    """Remove the space station from the file - its interior and exterior, their models, materials and textures"""

    bl_idname = "object.charon_forge_remove_station"
    bl_label = "Remove Space Station"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return station_library.find_station() is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for collection in station_library.find_stations():
            station_library.remove_station(collection)
        self.report({"INFO"}, "Removed the space station")
        return {"FINISHED"}


class CreateCircle(_CreateForged, bpy.types.Operator):
    """Turn the selected part into a flat circle of copies of it - rings, rows, spokes and more, with an edge of parts round it"""

    bl_idname = "object.charon_forge_create_circle"
    bl_label = "Circle"
    kind = Circle


class CreateSquare(_CreateForged, bpy.types.Operator):
    """Turn the selected part into a flat square of copies of it - its width and height can be set apart for a rectangle - filled in rows, bricks, frames and more, with edges of parts round it"""

    bl_idname = "object.charon_forge_create_square"
    bl_label = "Square"
    kind = Rectangle


class CreatePolygon(_CreateForged, bpy.types.Operator):
    """Turn the selected part into a flat polygon of copies of it - any number of sides, filled in frames, rows or wedges, with edges of parts round it"""

    bl_idname = "object.charon_forge_create_polygon"
    bl_label = "Polygon"
    kind = Polygon


classes = (
    CreateSphere,
    CreateShape,
    CreateCuboid,
    SplitForged,
    ResetForged,
    EditStation,
    RemoveStation,
    CreateCircle,
    CreateSquare,
    CreatePolygon,
)
