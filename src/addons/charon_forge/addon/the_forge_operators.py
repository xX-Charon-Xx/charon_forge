import bpy

from ..builder import station_design, station_library, station_prompt
from ..utils import qr_code, qr_forge, seed_utils
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
    colours: bpy.props.EnumProperty(
        name="Colours", description="The station palette to colour it with",
        items=station_library.palette_items,
    )
    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[
            ("DESIGN", "Design",
             "Build your own station, choosing its interior and every part of its exterior"),
            ("ADDRESS", "Galactic Address",
             "Build the station a system has in game, from its galactic address"),
        ],
    )
    address: bpy.props.StringProperty(
        name="Address",
        description="The system's galactic address - a save's GalacticAddress "
                    "(0x40050003AB8C07) or 12 portal glyphs (40050003AB8C, Euclid)",
    )
    use_modules: bpy.props.BoolProperty(
        name="Modules", description="With the exterior, the modules the system's "
                                    "station has around its body",
        default=True,
    )
    address_source: bpy.props.EnumProperty(
        name="Address From",
        items=[
            ("BASE", "Imported Base",
             "The address of the space station base imported into the scene"),
            ("CUSTOM", "Custom", "An address you type in"),
        ],
    )
    # opened for a space station base just imported, its address given
    from_base: bpy.props.BoolProperty(options={"HIDDEN", "SKIP_SAVE"})

    def _address(self, context):
        """The address the Galactic Address tab builds from: the imported
        base's, while there is one and it's chosen, else the typed one."""
        stored = station_prompt.stored_address(context.scene)
        if stored is not None and self.address_source == "BASE":
            return stored
        return self.address

    def invoke(self, context, event):
        # start from the station that's there: its parts ticked, their kinds
        # and colours chosen - and its address, if it was built from one
        stations = station_library.find_stations()
        if stations:
            interior = station_library.find_station(station_library.INTERIOR)
            exterior = station_library.find_station(station_library.EXTERIOR)
            self.use_interior = interior is not None
            self.use_exterior = exterior is not None
            if interior is not None:
                self.interior = interior[station_library.PROP_KIND]
            # a station that wasn't designed starts the design from its body
            if exterior is not None and not exterior.get(station_design.PROP_DESIGNED):
                try:
                    context.scene.charon_station_design.body = (
                        station_design.TYPE_GROUP + exterior[station_library.PROP_KIND])
                except TypeError:
                    pass
            try:
                self.colours = str(stations[0].get(station_library.PROP_PALETTE,
                                                   station_library.SAVED_PALETTE))
            except TypeError:
                pass
            seed = next((c[seed_utils.PROP_SEED] for c in stations
                         if seed_utils.PROP_SEED in c), None)
            designed = any(c.get(station_design.PROP_DESIGNED) for c in stations)
            if designed and not self.from_base:
                self.mode = "DESIGN"
            elif seed is not None and not self.from_base:
                self.mode = "ADDRESS"
                self.address = seed
                self.address_source = "CUSTOM"
        if self.from_base:
            # a base's own station, whole
            self.mode = "ADDRESS"
            self.address_source = "BASE"
            self.use_interior = self.use_exterior = self.use_modules = True
            return context.window_manager.invoke_props_dialog(
                self, title="Import This Base's Space Station", confirm_text="Import",
                width=340,
            )
        verb = "Modify" if stations else "Import"
        return context.window_manager.invoke_props_dialog(
            self, title="%s Space Station" % verb, confirm_text=verb, width=340
        )

    def draw(self, context):
        layout = self.layout
        if self.from_base:
            # opened for a base just imported: only its own station
            layout.label(text="This base is in a space station.", icon="INFO")
            layout.label(text="Build the station at its galactic address?")
            layout.separator()
            self._draw_address(context, layout)
            return
        layout.row().prop(self, "mode", expand=True)
        layout.separator()
        if self.mode == "ADDRESS":
            self._draw_address(context, layout)
            return
        self._draw_design(context, layout)

    def _draw_address(self, context, layout):
        # the imported space station base's address, or one typed in
        stored = station_prompt.stored_address(context.scene)
        if stored is not None:
            layout.row().prop(self, "address_source", expand=True)
        split = layout.split(factor=0.35, align=True)
        split.label(text="Address")
        if stored is not None and self.address_source == "BASE":
            split.label(text=stored, icon="HOME")
        else:
            split.prop(self, "address", text="")

        # what the address builds, worked out as it's typed
        config = _station_preview(self._address(context))
        if config is None:
            layout.label(text="Enter a galactic address or portal glyphs", icon="INFO")
        elif isinstance(config, str):
            layout.label(text=config, icon="ERROR")
        else:
            layout.label(text="%s exterior, %s interior, %d modules" % (
                station_library.kind_label(station_library.EXTERIOR, config["exterior"]),
                station_library.kind_label(station_library.INTERIOR, config["interior"]),
                len(config["modules"])))

        layout.separator()
        row = layout.row(align=True)
        row.prop(self, "use_interior")
        row.prop(self, "use_exterior")
        modules = row.row(align=True)
        modules.enabled = self.use_exterior
        modules.prop(self, "use_modules")

    def _draw_design(self, context, layout):
        design = context.scene.charon_station_design
        split = layout.split(factor=0.35, align=True)
        split.prop(self, "use_interior")
        interior = split.row(align=True)
        interior.enabled = self.use_interior
        interior.prop(self, "interior", text="")

        # the body, then each choice it has - indented under what opens it
        split = layout.split(factor=0.35, align=True)
        split.prop(self, "use_exterior")
        body = split.row(align=True)
        body.enabled = self.use_exterior
        body.prop(design, "body", text="")
        exterior = layout.column()
        exterior.enabled = self.use_exterior
        for depth, choice in station_design.visible(design):
            split = exterior.split(factor=0.35, align=True)
            label = split.row()
            label.separator(factor=1.0 + 1.5 * depth)
            label.label(text=choice.label)
            split.prop(design, choice.prop, text="")
        split = exterior.split(factor=0.35, align=True)
        split.label(text="")
        split.prop(design, "use_modules")

        exterior.separator()
        split = exterior.split(factor=0.35, align=True)
        split.label(text="Hull Colours")
        split.prop(design, "hull_colours", text="")
        split = exterior.split(factor=0.35, align=True)
        split.label(text="Hull Details")
        details = split.grid_flow(columns=2, align=True)
        for switch, _label, _description in station_design.HULL_DETAILS:
            details.prop(design, station_design.detail_prop(switch), toggle=True)
        interior_colours = layout.split(factor=0.35, align=True)
        interior_colours.enabled = self.use_interior
        interior_colours.label(text="Interior Colours")
        interior_colours.prop(self, "colours", text="")

    def execute(self, context):
        if self.mode == "ADDRESS":
            return _build_from_address(self, context)
        return _build_from_design(self, context)


def _station_preview(text, _cache={}):
    """What a typed address builds (seed_utils.station_config), an error
    message, or None with nothing typed. Kept per text, since the popup
    redraws it constantly."""
    if not text.strip():
        return None
    if text not in _cache:
        try:
            _cache.clear()
            _cache[text] = seed_utils.station_config(seed_utils.parse_address(text))
        except (ValueError, KeyError, StopIteration) as error:
            _cache[text] = "Not an address: %s" % text if isinstance(error, ValueError) \
                else "Can't work out this station: %s" % error
        except OSError as error:
            _cache[text] = "The station data is missing: %s" % error
    return _cache[text]


def _build_from_design(self, context):
    """EditStation's Design tab: a station built as designed, in place of
    whatever station is there."""
    design = context.scene.charon_station_design
    if not self.use_interior and not self.use_exterior:
        self.report({"WARNING"}, "Tick the interior, the exterior or both")
        return {"CANCELLED"}
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    palette = int(self.colours)

    # the station there is already this design - only its colours change,
    # nothing is loaded again
    key = station_design.design_key(design, self.use_interior, self.use_exterior,
                                    self.interior)
    stations = station_library.find_stations()
    if stations and all(c.get(station_design.PROP_DESIGN_KEY) == key for c in stations):
        for collection in stations:
            station_library.recolour(collection, palette)
        self.report({"INFO"}, "Recoloured the station")
        return {"FINISHED"}

    try:
        config, collections, missing = seed_utils.build_station(
            context, seed=station_design.hull_seed(design.hull_colours),
            interior=self.use_interior, exterior=self.use_exterior,
            modules=design.use_modules,
            interior_kind=self.interior if self.use_interior else None,
            palette_index=None if palette == station_library.SAVED_PALETTE else palette,
            layers=station_design.hull_layers(design),
            force=station_design.force(design),
        )
    except FileNotFoundError as error:
        self.report({"ERROR"}, "Station file not found: %s" % error)
        return {"CANCELLED"}
    for collection in collections:
        collection[station_design.PROP_DESIGNED] = True
        collection[station_design.PROP_DESIGN_KEY] = key
    station_library.set_selectable(False)
    if self.use_exterior:
        summary = "Built a %s station with %d modules" % (
            station_library.kind_label(station_library.EXTERIOR, config["exterior"]),
            len(config["modules"]) if design.use_modules else 0)
    else:
        summary = "Built a %s station interior" % station_library.kind_label(
            station_library.INTERIOR, config["interior"])
    if missing:
        summary += " - %d textures not found" % missing
    self.report({"WARNING"} if missing else {"INFO"}, summary)
    return {"FINISHED"}


def _build_from_address(self, context):
    """EditStation's Galactic Address tab: the system's own station, built by
    seed_utils in place of whatever station is there."""
    config = _station_preview(self._address(context))
    if not isinstance(config, dict):
        self.report({"ERROR"}, config or "Enter a galactic address")
        return {"CANCELLED"}
    if not self.use_interior and not self.use_exterior:
        self.report({"WARNING"}, "Tick the interior, the exterior or both")
        return {"CANCELLED"}
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    # the system's own colours: its palettes on the hull, and the interior's
    # base-building pieces as they were saved
    try:
        config, collections, missing = seed_utils.build_station(
            context, seed=config["seed"],
            interior=self.use_interior, exterior=self.use_exterior,
            modules=self.use_modules,
        )
    except FileNotFoundError as error:
        self.report({"ERROR"}, "Station file not found: %s" % error)
        return {"CANCELLED"}

    # the modules seed_utils places too - every piece is scenery
    station_library.set_selectable(False)
    summary = "Built the station of system 0x%X" % config["seed"]
    if config.get("baked"):
        summary += " - %d choices differ from the game's (see the console)" % len(config["baked"])
    if missing:
        summary += " - %d textures not found" % missing
    self.report({"WARNING"} if missing else {"INFO"}, summary)
    return {"FINISHED"}



class FrameStation(bpy.types.Operator):
    """Zoom the viewport onto part of the space station"""

    bl_idname = "view3d.charon_forge_frame_station"
    bl_label = "Frame Station"

    target: bpy.props.EnumProperty(
        items=[
            ("CORE", "Core", "The station's core - its main hall, floor and roof"),
            ("EXTERIOR", "Exterior", "The station's exterior"),
        ],
    )

    @classmethod
    def description(cls, context, properties):
        return "Zoom the viewport onto the station's %s" % properties.target.lower()

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == "VIEW_3D"

    def execute(self, context):
        if self.target == "CORE":
            objects = station_library.section_objects("CORE")
        else:
            objects = station_library.part_objects(station_library.EXTERIOR)
        if not station_library.frame_objects(context.space_data, objects):
            self.report({"WARNING"}, "There is no station %s to frame" % self.target.lower())
            return {"CANCELLED"}
        return {"FINISHED"}


class RemoveStation(bpy.types.Operator):
    """Remove parts of the space station from the file - its core, runway or exterior, with their models, materials and textures"""

    bl_idname = "object.charon_forge_remove_station"
    bl_label = "Remove Space Station"
    bl_options = {"REGISTER", "UNDO"}

    remove_core: bpy.props.BoolProperty(
        name="Core", description="Remove the interior's core - its main hall, floor and roof",
        default=True,
    )
    remove_runway: bpy.props.BoolProperty(
        name="Runway", description="Remove the interior's runway - its hangar, floor and roof",
        default=True,
    )
    remove_exterior: bpy.props.BoolProperty(
        name="Exterior", description="Remove the exterior - its body and modules",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        return station_library.find_station() is not None

    def invoke(self, context, event):
        # every part ticked, each time the popup opens
        self.remove_core = self.remove_runway = self.remove_exterior = True
        return context.window_manager.invoke_props_dialog(
            self, title="Remove Space Station", confirm_text="Remove"
        )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Remove these parts:")
        row = layout.row(align=True)
        has_interior = station_library.find_station(station_library.INTERIOR) is not None
        for name, present in (("core", has_interior), ("runway", has_interior),
                              ("exterior", station_library.find_station(
                                  station_library.EXTERIOR) is not None)):
            if present:
                row.prop(self, "remove_%s" % name)

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        removed = []
        for section, wanted in (("CORE", self.remove_core), ("RUNWAY", self.remove_runway)):
            if wanted and station_library.section_objects(section):
                station_library.remove_section(section)
                removed.append(section.lower())
        exterior = station_library.find_station(station_library.EXTERIOR)
        if self.remove_exterior and exterior is not None:
            station_library.remove_station(exterior)
            removed.append("exterior")
        if not removed:
            self.report({"INFO"}, "Nothing removed")
            return {"CANCELLED"}
        self.report({"INFO"}, "Removed the station's %s" % ", ".join(removed))
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


# the panel's long side over its short side, for the popup's panel estimate -
# the build itself measures the part
_QR_PANEL_RATIO = 2.4

# (text, level) -> (squares along a side, panels) or the error, for the popup
_qr_preview_cache = {}


def _qr_preview(text, level):
    """What the popup says about a code before it is forged. Cached, since
    the popup redraws on every keystroke."""
    key = (text, level)
    if key not in _qr_preview_cache:
        if len(_qr_preview_cache) > 32:
            _qr_preview_cache.clear()
        try:
            modules = qr_code.encode(text, level)
            _qr_preview_cache[key] = (len(modules), len(qr_forge.plan(modules, _QR_PANEL_RATIO)))
        except qr_code.QRCodeError as error:
            _qr_preview_cache[key] = str(error)
    return _qr_preview_cache[key]


class ForgeQRCode(bpy.types.Operator):
    """Build a QR code out of storage panels, at the 3D cursor"""

    # A forged code never gets scratched or smudged, so it takes the least
    # error correction a QR code can have - which is also the smallest code,
    # and the fewest panels. (There is no level with none at all.)
    ERROR_CORRECTION = "L"

    bl_idname = "object.charon_forge_qr_code"
    bl_label = "Forge a QR Code"
    bl_options = {"REGISTER", "UNDO"}

    text: bpy.props.StringProperty(
        name="Text",
        description="What the QR code says - a link, or any text",
    )
    module_size: bpy.props.FloatProperty(
        name="Square Size",
        description="How big one square of the code is",
        default=1.0, min=0.05, soft_max=10.0, unit="LENGTH",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self, width=380, title="Forge a QR Code", confirm_text="Forge",
        )

    def draw(self, context):
        layout = self.layout

        intro = layout.column(align=True)
        intro.scale_y = 0.8
        intro.label(text="Turns any text or link into a QR code", icon="INFO")
        intro.label(text="built from Storage Panels, at the 3D cursor.", icon="BLANK1")

        layout.separator()
        content = layout.box().column(align=True)
        content.label(text="Content", icon="TEXT")
        text_row = content.row()
        text_row.scale_y = 1.4
        text_row.activate_init = True
        text_row.prop(self, "text", text="", icon="LINKED" if "://" in self.text else "FONT_DATA")

        layout.separator()
        size_row = layout.row()
        size_row.scale_y = 1.2
        size_row.prop(self, "module_size")

        layout.separator()
        summary = layout.box().column(align=True)
        if not self.text.strip():
            summary.label(text="Enter some text to see the code's size", icon="QUESTION")
            return
        preview = _qr_preview(self.text.strip(), self.ERROR_CORRECTION)
        if isinstance(preview, str):
            summary.alert = True
            summary.label(text=preview.capitalize(), icon="ERROR")
            return
        squares, panels = preview
        summary.label(text=f"{squares} x {squares} squares", icon="MESH_GRID")
        summary.label(text=f"{squares * self.module_size:.1f} m across", icon="DRIVER_DISTANCE")
        summary.label(text=f"About {panels} panels", icon="MOD_ARRAY")

    def execute(self, context):
        text = self.text.strip()
        if not text:
            self.report({"ERROR"}, "Enter the text for the QR code")
            return {"CANCELLED"}

        name = "QR Code: " + (text if len(text) <= 24 else text[:24] + "...")
        try:
            objects, size = qr_forge.build_qr_code(
                text, self.ERROR_CORRECTION, self.module_size, collection_name=name,
            )
        except qr_code.QRCodeError as error:
            self.report({"ERROR"}, f"Could not make a QR code: {error}")
            return {"CANCELLED"}
        except Exception as error:                            # noqa: BLE001
            self.report({"ERROR"}, f"Could not forge the QR code: {error}")
            return {"CANCELLED"}

        _select_only(context, objects)
        self.report(
            {"INFO"},
            f"Forged a {size} x {size} QR code from {len(objects)} panels, in '{name}'",
        )
        return {"FINISHED"}


classes = (
    ForgeQRCode,
    CreateSphere,
    CreateShape,
    CreateCuboid,
    SplitForged,
    ResetForged,
    EditStation,
    FrameStation,
    RemoveStation,
    CreateCircle,
    CreateSquare,
    CreatePolygon,
)
