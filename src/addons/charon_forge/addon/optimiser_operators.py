import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty

from .. import materials
from ..utils import icon_utils, loading_overlay, optimiser_utils
from . import asset_browser_presentation


# Roughly 400px at blender's default ui scale - narrower than the add row
# popup, this one is a plain read out plus a rename field rather than
# something to search in.
EDIT_POPUP_WIDTH = 800

# How many rows the part list inside the edit popup shows before scrolling.
PART_LIST_ROWS = 15

# Roughly 700px at blender's default ui scale, which is what invoke_popup
# takes - it has no dpi aware unit, unlike a popover's bl_ui_units_x.
ADD_ROW_POPUP_WIDTH = 700



class OptimiseMaterials(bpy.types.Operator):
    """Make flat parts with the same ObjectID and UserData share one mesh"""

    bl_idname = "object.charon_optimise_materials"
    bl_label = "Optimise Materials"
    bl_options = {"REGISTER", "UNDO"}

    @loading_overlay.while_running("Optimising materials")
    def execute(self, context):
        materials.optimise_materials()
        optimiser = context.scene.charon_optimiser
        count = optimiser.optimise()
        self.report({"INFO"}, f"Optimised materials ({count} time(s) this session)")
        return {"FINISHED"}


class OptimiseNow(bpy.types.Operator):
    """Reorder the scene's parts now: parts in the priority list first, in
    its order, then everything else"""

    bl_idname = "object.charon_optimise_now"
    bl_label = "Optimise Now"

    @loading_overlay.while_running("Reordering parts")
    def execute(self, context):
        from ..builder import get_builder

        count = optimiser_utils.reorder_scene_objects(get_builder())
        self.report({"INFO"}, f"Reordered {count} part(s)")
        return {"FINISHED"}


class PriorityListMove(bpy.types.Operator):
    """Move a priority group up or down in the priority list"""

    bl_idname = "object.charon_priority_list_move"
    bl_label = "Move Priority Group"
    bl_options = {"INTERNAL"}

    index: IntProperty()
    direction: EnumProperty(
        items=[("UP", "Up", ""), ("DOWN", "Down", "")],
        default="UP",
    )

    def execute(self, context):
        optimiser = context.scene.charon_optimiser
        optimiser.move_priority_group(self.index, self.direction)
        return {"FINISHED"}


# The edit popup that is open, if any: which group it edits, and whether
# that group has been deleted from inside it. A button in the popup leaves it
# open, and with the group gone its index would point at the next group - so
# OK must not write anything once this says deleted.
_edit_session = {"index": None, "deleted": False}


class PriorityListDelete(bpy.types.Operator):
    """Remove this priority group, and every part in it, from the priority list"""

    bl_idname = "object.charon_priority_list_delete"
    bl_label = "Delete Priority Group"
    bl_options = {"INTERNAL"}

    index: IntProperty()

    def execute(self, context):
        optimiser = context.scene.charon_optimiser
        optimiser.delete_priority_group(self.index)
        if _edit_session["index"] == self.index:
            _edit_session["deleted"] = True
            optimiser.clear_priority_search()
        self.report({"INFO"}, "Priority group deleted")
        return {"FINISHED"}

class PriorityListDeletePart(bpy.types.Operator):
    """Remove one part from a priority group"""

    bl_idname = "object.charon_priority_list_delete_part"
    bl_label = "Remove Part"
    bl_options = {"INTERNAL"}

    index: IntProperty()
    object_id: StringProperty()

    def execute(self, context):
        priority_list = optimiser_utils.get_priority_list()
        if 0 <= self.index < len(priority_list):
            parts = optimiser_utils.get_group_parts(priority_list[self.index])
            parts.pop(self.object_id, None)
            optimiser_utils.save_priority_list(priority_list)

        optimiser = context.scene.charon_optimiser

        # a no-op if this id was never staged (it was an already saved part
        # being removed) - but if it was, the row rebuilt below would only
        # come back on OK unless it is dropped here too
        for staged_index, staged in enumerate(optimiser.priority_staged_additions):
            if staged.object_id == self.object_id:
                optimiser.priority_staged_additions.remove(staged_index)
                break

        # the edit popup's list is a scene collection, not read live off
        # disk each draw (see PriorityPartItem) - rebuild it so the removed
        # row is actually gone rather than just gone from the saved file.
        # Rebuilding from disk drops every staged preview row along with it,
        # so they are added back in - refresh_priority_part_list has no way
        # to know about staged, unsaved parts on its own.
        optimiser.refresh_priority_part_list(self.index)
        for staged in optimiser.priority_staged_additions:
            preview = optimiser.priority_part_list.add()
            preview.object_id = staged.object_id
            preview.nice_name = staged.nice_name

        for area in context.screen.areas:
            area.tag_redraw()

        return {"FINISHED"}


class PriorityListStagePart(bpy.types.Operator):
    """Move one search result into the group being edited

    Staged only - the priority list on disk is not touched until the edit
    popup's OK is pressed, see PriorityListEdit.execute.
    """

    bl_idname = "object.charon_priority_list_stage_part"
    bl_label = "Add Part"
    bl_options = {"INTERNAL"}

    object_id: StringProperty()
    nice_name: StringProperty()

    def execute(self, context):
        optimiser = context.scene.charon_optimiser
        optimiser.stage_priority_part(self.object_id, self.nice_name)

        for area in context.screen.areas:
            area.tag_redraw()

        return {"FINISHED"}


def _priority_search_category_items(self, context):
    """Reuse AssetBrowser's own category enum items.

    Both browser drop-downs the search side of the edit popup draws are
    read only views into whichever category/sub-category are already
    selected in the asset browser itself - the update happens once
    selection is confirmed, via PrioritySearchSelectCategory/SubCategory's
    execute rather than the browser's own update callbacks, so the search
    results collection is written from an operator rather than draw().
    """
    asset_browser = context.scene.nms_asset_browser
    return asset_browser.get_categories()


def _priority_search_sub_category_items(self, context):
    asset_browser = context.scene.nms_asset_browser
    return asset_browser.extract_enum_sub_categories()


class PrioritySearchSelectCategory(bpy.types.Operator):
    """Choose which category the search side of the edit popup browses"""

    bl_idname = "object.charon_priority_search_select_category"
    bl_label = "Category"
    bl_options = {"INTERNAL"}
    bl_property = "category"

    category: EnumProperty(items=_priority_search_category_items)

    def execute(self, context):
        asset_browser = context.scene.nms_asset_browser
        asset_browser.asset_browser_caterogies = self.category

        optimiser = context.scene.charon_optimiser
        optimiser.refresh_priority_search_results()

        for area in context.screen.areas:
            area.tag_redraw()

        return {"FINISHED"}

class PrioritySearchSelectSubCategory(bpy.types.Operator):
    """Choose which sub-category the search side of the edit popup browses"""

    bl_idname = "object.charon_priority_search_select_sub_category"
    bl_label = "Sub-Category"
    bl_options = {"INTERNAL"}
    bl_property = "sub_category"

    sub_category: EnumProperty(items=_priority_search_sub_category_items)

    def execute(self, context):
        asset_browser = context.scene.nms_asset_browser
        asset_browser.asset_browser_sub_caterogies = self.sub_category

        optimiser = context.scene.charon_optimiser
        optimiser.refresh_priority_search_results()

        for area in context.screen.areas:
            area.tag_redraw()

        return {"FINISHED"}

class PriorityListEdit(bpy.types.Operator):
    """Show every part in this priority group, and rename it"""

    bl_idname = "object.charon_priority_list_edit"
    bl_label = "Edit Priority Group"
    bl_options = {"INTERNAL"}

    index: IntProperty()
    # No update callback: invoke_props_dialog gives a real OK/Cancel, so
    # typing here only edits the operator's own copy - execute() is the one
    # place that writes it out, and only OK reaches execute at all.
    group_name: StringProperty(name="Name")

    def invoke(self, context, event):
        priority_list = optimiser_utils.get_priority_list()
        if 0 <= self.index < len(priority_list):
            self.group_name = optimiser_utils.get_group_name(
                priority_list[self.index]
            )

        # has to happen here rather than in draw(): draw() runs during
        # popup redraws, where blender does not let a scene collection's
        # writes stick - the same restriction that ruled out a UIList for
        # the group list this popup is opened from.
        optimiser = context.scene.charon_optimiser
        optimiser.refresh_priority_part_list(self.index)
        optimiser.clear_priority_search()
        _edit_session["index"] = self.index
        _edit_session["deleted"] = False

        return context.window_manager.invoke_props_dialog(
            self, width=EDIT_POPUP_WIDTH
        )

    def execute(self, context):
        # only reached on OK - Cancel (or Esc) never calls this, so a
        # rename or a staged addition left mid edit is simply discarded
        optimiser = context.scene.charon_optimiser

        # deleted from inside this popup: the index now points at another group
        deleted = _edit_session["deleted"] and _edit_session["index"] == self.index
        _edit_session["index"] = None
        _edit_session["deleted"] = False
        if deleted:
            optimiser.clear_priority_search()
            return {"FINISHED"}

        priority_list = optimiser_utils.get_priority_list()
        if 0 <= self.index < len(priority_list):
            group = priority_list[self.index]
            group["name"] = self.group_name.strip() or optimiser_utils.UNNAMED_GROUP_NAME

            parts = optimiser_utils.get_group_parts(group)
            for staged in optimiser.priority_staged_additions:
                parts[staged.object_id] = staged.nice_name
            group["parts"] = parts

            optimiser_utils.save_priority_list(priority_list)

        optimiser.clear_priority_search()
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        optimiser = context.scene.charon_optimiser

        if _edit_session["deleted"] and _edit_session["index"] == self.index:
            layout.label(text="This group has been deleted", icon="TRASH")
            layout.label(text="Close this window - nothing more will be saved", icon="BLANK1")
            return

        priority_list = optimiser_utils.get_priority_list()
        if self.index < 0 or self.index >= len(priority_list):
            layout.label(text="This group no longer exists", icon="ERROR")
            return

        # One row at a time across both halves, so the group's side and the
        # search side stay level: titles, then fields, then a status line,
        # then the two lists at the same height.
        def halves():
            split = layout.split(factor=0.5)
            return split.column(align=True), split.column(align=True)

        # titles
        left, right = halves()
        left.label(text="Title")
        right.label(text="Add Parts")

        # the group's name, with a button to delete the whole group - and the
        # search box
        left, right = halves()
        name_row = left.row(align=True)
        name_row.prop(self, "group_name", text="")
        delete = name_row.operator(PriorityListDelete.bl_idname, text="", icon="TRASH")
        delete.index = self.index
        right.prop(optimiser, "priority_search_query", text="", icon="VIEWZOOM")

        layout.separator()

        # status line: what the group holds, and how the search stands
        query = (optimiser.priority_search_query or "").strip()
        left, right = halves()
        part_count = len(optimiser.priority_part_list)
        staged = len(optimiser.priority_staged_additions)
        if staged:
            left.label(text=f"Objects List - {staged} staged, added on OK", icon="ADD")
        elif part_count:
            left.label(text=f"Objects List ({part_count})")
        else:
            left.label(text="Objects List - no items yet")

        if not query:
            # category / sub-category browse, like the asset browser's list view
            asset_browser = context.scene.nms_asset_browser
            browse_row = right.row(align=True)
            browse_row.operator_menu_enum(
                PrioritySearchSelectCategory.bl_idname, "category",
                text=asset_browser.asset_browser_caterogies or "Category",
            )
            browse_row.operator_menu_enum(
                PrioritySearchSelectSubCategory.bl_idname, "sub_category",
                text=asset_browser.asset_browser_sub_caterogies or "All",
            )
        elif len(query) < 3:
            right.label(text="Type at least three characters", icon="INFO")
        elif not optimiser.priority_search_result_list:
            right.label(text="Nothing matches", icon="INFO")
        else:
            right.label(text=f"{len(optimiser.priority_search_result_list)} found")

        # the lists, the same height; the right one's rows have an add button
        # instead of a remove one - see optimiser_presentation
        left, right = halves()
        left.template_list(
            "CHARON_UL_priority_part_list", "",
            optimiser, "priority_part_list",
            optimiser, "priority_part_list_index",
            rows=PART_LIST_ROWS,
        )
        right.template_list(
            "CHARON_UL_priority_search_result_list", "",
            optimiser, "priority_search_result_list",
            optimiser, "priority_search_result_list_index",
            rows=PART_LIST_ROWS,
        )


class PriorityListAddRow(bpy.types.Operator):
    """Add a new priority group"""

    bl_idname = "object.charon_priority_list_add_row"
    bl_label = "Add Row"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        # start on a clean search rather than whatever the asset browser or
        # the header menu was last looking at
        asset_browser = context.scene.nms_asset_browser
        asset_browser.asset_broser_search_query = ""
        return context.window_manager.invoke_popup(
            self, width=ADD_ROW_POPUP_WIDTH
        )

    def execute(self, context):
        optimiser = context.scene.charon_optimiser
        optimiser.add_priority_group()
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        asset_browser = context.scene.nms_asset_browser

        search_column = layout.column(align=True)
        search_column.label(text="Search Items")
        # the same property the header menu searches on, so its update
        # callback does the filtering for us - see AssetBrowser.on_search_entered
        search_column.prop(
            asset_browser, "asset_broser_search_query", text="", icon="VIEWZOOM"
        )

        layout.separator()

        if asset_browser.enum_asset_browser_what_to_display != "search":
            layout.label(text="Type at least three characters to search")
            return

        search_data = asset_browser.get_search_results()
        if not search_data:
            layout.label(text="No Items")
            return

        try:
            pcoll = icon_utils.get_asset_icons_pcoll()
        except KeyError:
            pcoll = None

        results_row = layout.row(align=True)
        for sub_category, object_ids in search_data.items():
            asset_browser_presentation.draw_sub_category(
                pcoll=pcoll,
                container=results_row,
                label=sub_category,
                elements_list=object_ids,
                number_of_columns=4,
                icon_size=2,
                grid_type="Other",
                show_title=False,
            )


class PriorityListReset(bpy.types.Operator):
    """Discard your changes and go back to the priority list the addon ships with"""

    bl_idname = "object.charon_priority_list_reset"
    bl_label = "Reset Priority List"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        optimiser = context.scene.charon_optimiser
        optimiser.reset_priority_list()
        self.report({"INFO"}, "Priority list reset to the shipped default")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


classes = (
    OptimiseMaterials,
    OptimiseNow,
    PriorityListMove,
    PriorityListDelete,
    PriorityListDeletePart,
    PriorityListStagePart,
    PrioritySearchSelectCategory,
    PrioritySearchSelectSubCategory,
    PriorityListEdit,
    PriorityListAddRow,
    PriorityListReset,
)
