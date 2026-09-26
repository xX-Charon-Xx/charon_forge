import bpy
from bpy.props import (BoolProperty, CollectionProperty, IntProperty, PointerProperty,
                       StringProperty)

from . import optimiser_operators, optimiser_presentation
from ..utils import optimiser_utils


class PriorityPartItem(bpy.types.PropertyGroup):
    """One row of the edit popup's part list.

    A scene level collection rather than reading the saved list straight
    into the UIList's draw_item: it needs to exist and be populated before
    invoke_props_dialog is called, from PriorityListEdit.invoke - see
    Optimiser.refresh_priority_part_list. Populating it from draw() itself
    would not stick, the same restriction that ruled out a UIList for the
    priority group list this is nested inside of.
    """

    object_id: StringProperty()
    nice_name: StringProperty()


# State for the optimiser panel, stored on the scene as scene.charon_optimiser.
class Optimiser(bpy.types.PropertyGroup):

    # how many times materials.optimise_materials() has been run this session
    optimise_count: IntProperty(
        name="Optimise Count",
        default=0,
        min=0,
    )

    # the corvette's main parts, picked by hand
    use_primary_parts: BoolProperty(
        name="Select Primary Corvette Parts",
        description="Choose which parts are the corvette's cockpit and landing bay",
        default=False,
    )
    cockpit: PointerProperty(
        name="Cockpit", description="The corvette's cockpit", type=bpy.types.Object,
    )
    landing_bay: PointerProperty(
        name="Landing Bay", description="The corvette's landing bay", type=bpy.types.Object,
    )

    def optimise(self):
        self.optimise_count += 1
        return self.optimise_count

    # Rows for the edit popup's part list - see PriorityPartItem.
    priority_part_list: CollectionProperty(type=PriorityPartItem)
    priority_part_list_index: IntProperty()

    # Which priority group priority_part_list belongs to. Stored so the
    # UIList's draw_item, which only ever gets (data, item) and not the
    # operator that opened the popup, can still say which group its remove
    # button should edit - see optimiser_presentation.CHARON_UL_priority_part_list.
    priority_part_list_group_index: IntProperty()

    def refresh_priority_part_list(self, group_index):
        """Rebuild the part list rows for one priority group.

        Staged additions (see priority_staged_additions) are appended after
        the saved parts - they are only a preview until OK is pressed, and
        this is the one place that rebuilds priority_part_list from disk, so
        it is also the one place they would otherwise get lost from view.
        """
        self.priority_part_list.clear()
        self.priority_part_list_group_index = group_index

        priority_list = optimiser_utils.get_priority_list()
        if 0 <= group_index < len(priority_list):
            parts = optimiser_utils.get_group_parts(priority_list[group_index])
            for object_id, nice_name in parts.items():
                item = self.priority_part_list.add()
                item.object_id = object_id
                item.nice_name = nice_name

        for staged in self.priority_staged_additions:
            item = self.priority_part_list.add()
            item.object_id = staged.object_id
            item.nice_name = staged.nice_name

    # Search results and staged additions for the edit popup's right hand
    # column - see PriorityListEdit. Both live here rather than on the
    # operator instance: the search field's own update callback and the add
    # button are each a separate call into blender, with no operator
    # instance in common to hold state on.
    priority_search_query: StringProperty(
        name="Search",
        description="Search for parts to add to this priority group",
        # without this the update callback only fires on enter or losing
        # focus - see AssetBrowser.asset_broser_search_query for the same fix
        options={'TEXTEDIT_UPDATE'},
        update=lambda self, context: self.refresh_priority_search_results(),
    )
    priority_search_result_list: CollectionProperty(type=PriorityPartItem)
    priority_search_result_list_index: IntProperty()

    # Staged additions, applied to the saved list only when the edit popup
    # is confirmed - see PriorityListEdit.execute. Not written to disk on
    # every add click, the same way the rename field is not.
    priority_staged_additions: CollectionProperty(type=PriorityPartItem)

    def _fill_priority_search_results(self, objects_by_sub_category):
        """Common tail of refresh_priority_search_results: dedupe and fill.

        Args:
            objects_by_sub_category (dict): {sub category: {object id: part
                data}}, ids without the "^" the priority list's own use.
        """
        self.priority_search_result_list.clear()

        staged_ids = {item.object_id for item in self.priority_staged_additions}
        existing_ids = {item.object_id for item in self.priority_part_list}

        for objects_list in objects_by_sub_category.values():
            for object_id, part_data in objects_list.items():
                # ids in the category tree have no "^" - the priority list's
                # own ids do, see optimiser_presentation's icon lookups
                full_id = "^" + object_id
                if full_id in staged_ids or full_id in existing_ids:
                    continue

                item = self.priority_search_result_list.add()
                item.object_id = full_id
                item.nice_name = part_data.get("name", object_id)

    def refresh_priority_search_results(self):
        """Rebuild the search result rows.

        Typing a query of three characters or more searches every category;
        an empty query instead browses whatever category/sub-category is
        selected in the two enums below the search bar, falling back to the
        first category the same way the asset browser's own list view does -
        see asset_browser_utils.resolve_sub_categories.

        Runs from the search field's and the two enums' own update callbacks
        - triggered by editing them, not by a redraw - so writing the
        collection here is safe the same way AssetBrowser.on_search_entered's
        write is.
        """
        from ..utils import asset_browser_utils

        asset_browser = bpy.context.scene.nms_asset_browser
        categories_data = asset_browser.get_categories_data()

        query = (self.priority_search_query or "").strip()
        if len(query) >= 3:
            results = asset_browser_utils.filter_objects(categories_data, query)
        elif query:
            # 1-2 characters: neither a search (too short) nor empty (browse
            # mode) - nothing to show rather than either
            self.priority_search_result_list.clear()
            return
        else:
            results = asset_browser_utils.resolve_sub_categories(
                categories_data,
                asset_browser.asset_browser_caterogies,
                asset_browser.asset_browser_sub_caterogies,
            )

        self._fill_priority_search_results(results)

    def stage_priority_part(self, object_id, nice_name):
        """Move one search result into the staged additions list.

        Also appended straight into priority_part_list, so it shows in the
        left hand list immediately rather than only after OK is pressed -
        that list is otherwise only rebuilt from disk, which staging does
        not touch yet. priority_staged_additions stays the source of truth
        for what execute() actually saves; the row added here is purely the
        preview of it.
        """
        for index, item in enumerate(self.priority_search_result_list):
            if item.object_id == object_id:
                self.priority_search_result_list.remove(index)
                break

        staged = self.priority_staged_additions.add()
        staged.object_id = object_id
        staged.nice_name = nice_name

        preview = self.priority_part_list.add()
        preview.object_id = object_id
        preview.nice_name = nice_name

    def clear_priority_search(self):
        """Reset the right hand column for a freshly opened edit popup.

        Left showing the first category's items rather than empty: an empty
        priority_search_query means "browse" (see
        refresh_priority_search_results), and the property assignment below
        does not reliably re-fire its own update callback when the string is
        already blank, so the refresh is called directly instead of counting
        on that.
        """
        self.priority_search_query = ""
        self.priority_staged_additions.clear()
        self.refresh_priority_search_results()

    # The priority list itself is not mirrored onto the scene - the panel
    # reads it straight off disk through optimiser_utils.get_cached_priority_list.
    # A scene collection needed filling in from outside the draw pass, which
    # is what kept the old UIList version showing an empty list.
    def move_priority_group(self, index, direction):
        """Swap the group at index with its neighbour, then save."""
        priority_list = optimiser_utils.get_priority_list()
        if index < 0 or index >= len(priority_list):
            return

        target = index + (-1 if direction == "UP" else 1)
        if target < 0 or target >= len(priority_list):
            return

        priority_list[index], priority_list[target] = (
            priority_list[target],
            priority_list[index],
        )
        optimiser_utils.save_priority_list(priority_list)

    def delete_priority_group(self, index):
        """Remove the group at index, then save."""
        priority_list = optimiser_utils.get_priority_list()
        if index < 0 or index >= len(priority_list):
            return

        del priority_list[index]
        optimiser_utils.save_priority_list(priority_list)

    def add_priority_group(self):
        """Append an empty, unnamed group to the end of the list, then save."""
        priority_list = optimiser_utils.get_priority_list()
        priority_list.append(optimiser_utils.new_priority_group())
        optimiser_utils.save_priority_list(priority_list)

    def reset_priority_list(self):
        """Throw the user's edits away and go back to the shipped list."""
        optimiser_utils.reset_priority_list()


classes = (
    PriorityPartItem,
    Optimiser,
) + optimiser_operators.classes + optimiser_presentation.classes


def register():
    for _class in classes:
        bpy.utils.register_class(_class)
    bpy.types.Scene.charon_optimiser = PointerProperty(type=Optimiser)


def unregister():
    del bpy.types.Scene.charon_optimiser
    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)
