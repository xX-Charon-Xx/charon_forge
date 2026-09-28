import bpy
from bpy.types import Panel

from ..builder import station_library
from ..objects.shapes.circle import Circle
from ..objects.shapes.cuboid import Cuboid
from ..objects.shapes.forged import Forged
from ..objects.shapes.polygon import Polygon
from ..objects.shapes.rectangle import Rectangle
from ..objects.shapes.shape import Shape
from ..objects.shapes.sphere import Sphere
from ..objects.shapes.text import Text
from ..utils import icon_utils
from ..objects.shapes import circle_topology, panel_font, shape_topology
from .the_forge_operators import (
    CreateCircle,
    CreateCuboid,
    CreatePolygon,
    CreateShape,
    CreateSphere,
    CreateSquare,
    EditStation,
    ForgeQRCode,
    ForgeText,
    FrameStation,
    RemoveStation,
    ResetForged,
    SplitForged,
    forge_source_problem,
)


# built in icons this blender has - QRCODE isn't in every version
_ICONS = {
    item.identifier
    for item in bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items
}


# The Forge Panel ---
class CHARON_PT_the_forge_panel(Panel):
    bl_idname = "CHARON_PT_the_forge_panel"
    bl_label = "The Forge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Charon Forge"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout

        # laid out like the crossing/optimiser panels: the icon on the left,
        # the description and controls in a column beside it
        description_row = layout.row(align=True)
        description_row.scale_y = 0.6
        description_icon_row = description_row.row(align=True)
        description_icon_row.scale_x = 1.1
        description_icon_row.template_icon(
            icon_value=icon_utils.get_icon_id("the_forge"),
            scale=3,
        )
        description_column = description_row.column(align=True)
        description_column.separator()
        description_column.label(text="Forge new parts and")
        description_column.label(text="shape them into ships")

        #layout.separator()
        
        active_object = context.active_object
        editing = Forged.is_forged(active_object)
        if editing:
            box = layout.box()  
            settings = active_object.charon_forged
            if settings.form == Circle.FORM:
                draw_circle_settings(box, settings)
            elif settings.form == Rectangle.FORM:
                draw_rectangle_settings(box, settings)
            elif settings.form == Polygon.FORM:
                draw_polygon_settings(box, settings)
            elif settings.form == Cuboid.FORM:
                draw_cuboid_settings(box, settings)
            elif settings.form == Shape.FORM:
                draw_shape_settings(box, settings)
            elif settings.form == Sphere.FORM:
                draw_sphere_settings(box, settings)
            elif settings.form == Text.FORM:
                draw_text_settings(box, settings)
            row = box.row()
            row.operator(ResetForged.bl_idname, icon="LOOP_BACK")
            row.operator(SplitForged.bl_idname, icon="MOD_EXPLODE")
            layout.separator()

        # everything else stays in view while a shape or text is being edited,
        # greyed out only while it is selected as well as active - Blender
        # keeps a deselected object active
        rest = layout.column()
        rest.enabled = not (editing and active_object.select_get())

        box = rest.box()
        forge_shape_col = box.column(align = True)
        forge_shape_col.label(text = "Forge a Shape")
        forge_shape_col.label(text="3D Shape")
        row = forge_shape_col.row(align=True)
        row.operator(CreateSphere.bl_idname, icon="MESH_UVSPHERE")
        row.operator(CreateCuboid.bl_idname, icon="MESH_CUBE")
        row.operator(CreateShape.bl_idname, icon="MESH_ICOSPHERE")
        forge_shape_col.separator()
        forge_shape_col.label(text="2D Shape")
        row = forge_shape_col.row(align=True)
        row.operator(CreateCircle.bl_idname, icon="MESH_CIRCLE")
        row.operator(CreateSquare.bl_idname, icon="MESH_PLANE")
        row.operator(CreatePolygon.bl_idname, icon="SEQ_CHROMA_SCOPE")

        symbol_box = rest.box()
        symbol_col = symbol_box.column(align=True)
        symbol_col.label(text="Forge a Symbol")
        row = symbol_col.row(align=True)
        row.operator(ForgeQRCode.bl_idname, text="QR Code",
                     icon="QRCODE" if "QRCODE" in _ICONS else "TEXTURE")
        row.operator(ForgeText.bl_idname, text="Text", icon="FONT_DATA")

        station_box = rest.box()
        station_box.label(text="Forge Space Station", icon="WORLD")
        if not station_library.find_stations():
            station_box.operator(EditStation.bl_idname, text="Import Space Station",
                                 icon="IMPORT")
        else:
            # the parts there are side by side, each interior section with its
            # roof tucked in under it - which only matters while it's showing
            forge = context.scene.charon_the_forge
            visibility_col = station_box.column(align=True)
            visibility_col.label(text="Visibility")
            parts_row = visibility_col.row()
            # a section taken out on its own has nothing left to show
            for section in ("core", "runway"):
                if station_library.section_objects(section.upper()):
                    column = parts_row.column(align=True)
                    column.prop(forge, "show_station_%s" % section)
                    roof = column.row(align=True)
                    roof.separator(factor=2.0)
                    roof.enabled = getattr(forge, "show_station_%s" % section)
                    roof.prop(forge, "show_station_%s_roof" % section)
            has_exterior = station_library.find_station(station_library.EXTERIOR) is not None
            if has_exterior:
                parts_row.column(align=True).prop(forge, "show_station_exterior")
            visibility_col.separator(factor=0.5)
            visibility_col.prop(forge, "station_selectable")

            frame_row = station_box.row(align=True)
            core = frame_row.row(align=True)
            core.enabled = bool(station_library.section_objects("CORE"))
            core.operator(FrameStation.bl_idname, text="Frame Core",
                          icon="ZOOM_SELECTED").target = "CORE"
            exterior = frame_row.row(align=True)
            exterior.enabled = has_exterior
            exterior.operator(FrameStation.bl_idname, text="Frame Exterior",
                              icon="ZOOM_ALL").target = "EXTERIOR"

            station_box.separator(factor=0.3)
            row = station_box.row(align=True)
            row.operator(EditStation.bl_idname, text="Modify Space Station",
                         icon="MODIFIER")
            row.operator(RemoveStation.bl_idname, text="", icon="TRASH")


# what the rings and segments counts are called in each topology; None hides
# one it doesn't use
_COUNT_LABELS = {
    "RINGS": ("Rings", "Around"),
    "MERIDIANS": ("Along", "Meridians"),
    "GEODESIC": ("Frequency", None),
    "CUBE": ("Grid", None),
    "SPIRAL": (None, "Copies"),
}


def draw_sphere_settings(layout, forge):
    """The settings of the active sphere."""
    _draw_title(layout, forge, "MESH_UVSPHERE")
    _draw_pattern(layout, forge, "topology", "Topology")

    column = _section(layout, "Sphere")
    row = column.row(align=True)
    row.prop(forge, "radius")
    row.prop(forge, "tile_scale", text="Part Size")
    rings_label, segments_label = _COUNT_LABELS.get(forge.topology, ("Rings", "Around"))
    counts_row = column.row(align=True)
    if rings_label:
        counts_row.prop(forge, "rings", text=rings_label)
    if segments_label:
        counts_row.prop(forge, "segments", text=segments_label)
    if forge.topology == "RINGS":
        column.prop(forge, "pole_density")
    column.prop(forge, "pole_part_size")

    column = _section(layout, "Shape")
    span_row = column.row(align=True)
    span_row.prop(forge, "top")
    span_row.prop(forge, "bottom")
    sweep_row = column.row(align=True)
    sweep_row.prop(forge, "sweep_start", text="Start")
    sweep_row.prop(forge, "sweep_end", text="End")
    _draw_inline(column, forge, "sphere_scale", "Stretch", factor=0.2)
    _draw_inline(column, forge, "rotation", "Rot", factor=0.2)


def draw_shape_settings(layout, forge):
    """The settings of the active shape."""
    _draw_title(layout, forge, "MESH_ICOSPHERE")
    _draw_pattern(layout, forge, "shape_style", "Style")

    column = _section(layout, "Shape")
    _draw_pair(column, forge, "size", "tile_scale", second_text="Part Size")
    _draw_style_options(column, forge)

    column = _section(layout, "Faces")
    _draw_pair(column, forge, "face_margin", "spacing", first_text="Margin")
    follow_row = column.row(align=True)
    follow_row.prop(forge, "follow_edges")
    if forge.follow_edges:
        follow_row.prop(forge, "corner_overlap", text="Overlap")
    _draw_inline(column, forge, "stretch", "Stretch", factor=0.2)
    _draw_inline(column, forge, "rotation", "Rot", factor=0.2)


def draw_cuboid_settings(layout, forge):
    """The settings of the active cuboid - its faces are filled corner to
    corner, so it has no Follow Edges or Corner Overlap."""
    _draw_title(layout, forge, "MESH_CUBE")
    split = layout.split(factor=0.3, align=True)
    split.label(text="Part:")
    split.prop(forge, "part_shape", text="",
               icon="TRIA_UP" if Forged.is_triangle(forge) else "MESH_PLANE")

    column = _section(layout, "Cuboid")
    _draw_pair(column, forge, "size", "tile_scale", second_text="Part Size")
    _draw_pair(column, forge, "face_margin", "spacing", first_text="Offset")
    _draw_inline(column, forge, "dimensions", "Shape", factor=0.2)
    _draw_inline(column, forge, "rotation", "Rot", factor=0.2)


def draw_circle_settings(layout, forge):
    """The settings of the active circle - the one 2D shape that can line
    its outline too."""
    _draw_title(layout, forge, "MESH_CIRCLE")
    _draw_pattern(layout, forge, "circle_topology", "Pattern")

    column = _section(layout, "Circle")
    _draw_pair(column, forge, "radius", "tile_scale", second_text="Part Size")
    column.prop(forge, "hole_size")
    arc_row = column.row(align=True)
    arc_row.prop(forge, "sweep_start", text="Arc Start")
    arc_row.prop(forge, "sweep_end", text="Arc End")

    column = _section(layout, "Fill")
    column.row(align=True).prop(forge, "circle_fill", expand=True)
    _draw_pair(column, forge, "face_margin", "spacing", first_text="Margin")
    if forge.circle_fill == circle_topology.FACE:
        topology = forge.circle_topology
        if topology == circle_topology.SPOKES:
            column.prop(forge, "spokes")
        if topology == circle_topology.SPIRAL:
            column.prop(forge, "spiral_arms")
        if topology in circle_topology.DENSITY_TOPOLOGIES:
            column.prop(forge, "centre_density")
        if topology in (circle_topology.RINGS, circle_topology.GRID):
            column.prop(forge, "stagger")
    else:
        column.row(align=True).prop(forge, "rim_style", expand=True)

    column = _section(layout, "Shape")
    _draw_inline(column, forge, "circle_scale", "Stretch", factor=0.2)
    _draw_inline(column, forge, "rotation", "Rot", factor=0.2)


def draw_rectangle_settings(layout, forge):
    """The settings of the active square - a rectangle once its width and
    height differ."""
    _draw_title(layout, forge, "MESH_PLANE")
    _draw_pattern(layout, forge, "rect_topology", "Pattern")

    column = _section(layout, "Square")
    _draw_pair(column, forge, "hole_size", "tile_scale", second_text="Part Size")
    _draw_pair(column, forge, "face_margin", "spacing", first_text="Margin")
    _draw_inline(column, forge, "rect_size", "Size", factor=0.2)
    _draw_inline(column, forge, "rotation", "Rot", factor=0.2)


def draw_text_settings(layout, forge):
    """The settings of the active text - its panels are sized by the
    letters, so it has no Part Size or Rotation."""
    _draw_title(layout, forge, "FONT_DATA")
    text_row = layout.row()
    text_row.scale_y = 1.3
    text_row.prop(forge, "text_body", text="", icon="TEXT")
    _draw_inline(layout, forge, "text_font", "Font")
    style_row = layout.row(align=True)
    bold = style_row.row(align=True)
    # a family already as heavy as it goes, or drawn freehand, has no bold -
    # and one leaning over already no italic
    bold.enabled = panel_font.has_bold(forge.text_font)
    bold.prop(forge, "text_bold", toggle=True)
    italic = style_row.row(align=True)
    italic.enabled = panel_font.has_italic(forge.text_font)
    italic.prop(forge, "text_italic", toggle=True)

    column = _section(layout, "Letters")
    _draw_pair(column, forge, "letter_height", "letter_spacing",
               first_text="Height", second_text="Spacing")
    if forge.shape_info:
        info = column.row()
        info.enabled = False
        info.label(text=forge.shape_info, icon="DRIVER_DISTANCE")


def draw_polygon_settings(layout, forge):
    """The settings of the active polygon."""
    _draw_title(layout, forge, "SEQ_CHROMA_SCOPE")
    _draw_pattern(layout, forge, "polygon_topology", "Pattern")

    column = _section(layout, "Polygon")
    _draw_pair(column, forge, "polygon_sides", "radius")
    _draw_pair(column, forge, "hole_size", "tile_scale", second_text="Part Size")
    _draw_pair(column, forge, "face_margin", "spacing", first_text="Margin")
    _draw_inline(column, forge, "circle_scale", "Stretch", factor=0.2)
    _draw_inline(column, forge, "rotation", "Rot", factor=0.2)


def _draw_style_options(column, forge):
    """The options of the shape's style - a corner count for the hull
    styles, the ones each built shape needs for the rest."""
    style = forge.shape_style
    if style in shape_topology.HULL_STYLES:
        column.prop(forge, "vertices")
        return

    column.prop(forge, "sides", text="Points" if style == shape_topology.STAR else "Sides")
    if style == shape_topology.TORUS:
        column.prop(forge, "tube_sides")
        column.prop(forge, "thickness")
    if style == shape_topology.CAPSULE:
        column.prop(forge, "cap_rings")
    if style in (shape_topology.CYLINDER, shape_topology.CONE, shape_topology.CAPSULE,
                 shape_topology.STAR):
        column.prop(forge, "shape_height")
    if style == shape_topology.CONE:
        column.prop(forge, "top_size")
    if style == shape_topology.STAR:
        column.prop(forge, "inner_size")
    if style in shape_topology.SWEPT_STYLES:
        column.prop(forge, "shape_sweep")

    # a donut or capsule only has ends to close once it is cut short
    whole = forge.shape_sweep >= shape_topology.FULL_TURN - 1e-4
    if style in (shape_topology.TORUS, shape_topology.CAPSULE) and whole:
        return
    column.prop(forge, "capped")


# Shared pieces - every kind's settings are laid out the same way: the part
# and its count, the pattern, its own settings in pairs, then its stretch and
# the parts' rotation, each on one line ---
def _draw_title(layout, forge, icon):
    """The part's name, and on the right how many copies of it there are -
    or why the layout couldn't be built."""
    header = layout.row()
    header.label(text=forge.object_id, icon=icon)
    status = header.row()
    status.alignment = "RIGHT"
    if forge.message:
        status.label(text=forge.message, icon="ERROR")
    else:
        status.label(text=f"({forge.part_count} parts)")


def _draw_pattern(layout, forge, name, title):
    """The pattern, and on its right what shape the part is laid as - its
    icon the shape Auto found."""
    split = layout.split(factor=0.3, align=True)
    split.label(text=f"{title}:")
    row = split.row(align=True)
    row.prop(forge, name, text="")
    shape = row.row(align=True)
    shape.ui_units_x = 4.5
    shape.prop(forge, "part_shape", text="",
               icon="TRIA_UP" if Forged.is_triangle(forge) else "MESH_PLANE")


def _section(layout, title):
    column = layout.column(align=True)
    column.label(text=title)
    return column


def _draw_pair(column, forge, first, second, first_text=None, second_text=None):
    """Two settings side by side."""
    row = column.row(align=True)
    row.prop(forge, first, **({"text": first_text} if first_text else {}))
    row.prop(forge, second, **({"text": second_text} if second_text else {}))


def _draw_inline(layout, forge, name, title, factor=0.3):
    """A label and its setting on one line, the label taking `factor` of it."""
    split = layout.split(factor=factor, align=True)
    split.label(text=f"{title}:")
    split.row(align=True).prop(forge, name, text="")


classes = (
    CHARON_PT_the_forge_panel,
)
