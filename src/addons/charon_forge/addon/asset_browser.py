
import bpy
from . import asset_browser_operators, asset_browser_presentation
from ..utils import asset_browser_utils
from ..utils.fallbacks.blend_utils import ShowMessageBox


ADDON_ID = asset_browser_utils.ADDON_ID
RECENTS_LIMIT = asset_browser_utils.RECENTS_LIMIT

# Re-exported so the panels and operators can keep importing them from here.
get_preferences = asset_browser_utils.get_preferences
load_json_preference = asset_browser_utils.load_json_preference
load_stored_list = asset_browser_utils.load_stored_list


class NMSCategoryOrderItem(bpy.types.PropertyGroup):
    """One row of the category reorder list, and of the main category list.
    row_kind is only set on the main list; reorder rows keep the default."""

    category_name: bpy.props.StringProperty()
    is_fav: bpy.props.BoolProperty()
    row_kind: bpy.props.StringProperty(default="category")


# Non-category rows at the top of the main category list - see
# refresh_category_list and NMS_UL_asset_browser_category.draw_item.
SPECIAL_LIST_ROWS = (
    ("fav", "Favourite Items", "FUND"),
    ("recent", "Recent Items", "RECOVER_LAST"),
    ("preset", "Presets", "ASSET_MANAGER"),
)


def _refresh_category_list():
    """Timer callback that builds the category rows after a redraw; runs once."""
    scene = getattr(bpy.context, "scene", None)
    asset_browser = getattr(scene, "nms_asset_browser", None) if scene else None
    if asset_browser is not None:
        asset_browser.refresh_category_list()
    return None


class AssetBrowser(bpy.types.PropertyGroup):
    """The asset browser's Blender state: properties, enum callbacks and their caches.
    The data work lives in utils/asset_browser_utils.py."""

    enum_categories = []
    enum_sub_categories = []

    check_display_search_results: bpy.props.BoolProperty(
        name = "Display Search Results",
        default = False
    )

    # The header menu's search - its own query, so it and the browser's
    # search box can each hold something different
    quick_search_query: bpy.props.StringProperty(
        name="Search Items",
        description="Search every part by name or id",
        default="",
        options={'TEXTEDIT_UPDATE'},
    )

    asset_broser_search_query: bpy.props.StringProperty(
        name="Search",
        default="",
        options={'TEXTEDIT_UPDATE'},
        update = lambda self, context: self.on_search_entered()
    )

    asset_browser_caterogies: bpy.props.EnumProperty(
        name="Categories",
        description="Catagories",
        items = lambda self, context: self.get_categories(),
        update = lambda self, context: self.on_category_selected(),
        default = 0
    )

    asset_browser_sub_caterogies: bpy.props.EnumProperty(
        name="Subcategory",
        description="Subcategory",
        # asked for directly rather than read off a class attribute that update
        # callbacks reassign, so the entries always match the chosen category
        items = lambda self, context: self.extract_enum_sub_categories(),
        update=lambda self, context: self.on_sub_category_selected(),
    )

    enum_asset_browser_mode: bpy.props.EnumProperty(
        name="View Mode",
        description="Asset Browser View Mode",
        items = [
            ("List", "List", "List","ALIGN_LEFT", 0),
            ("Grid", "Grid", "Grid","LIGHTPROBE_VOLUME",1)
        ],
        default = "Grid"
    )

    enum_asset_browser_what_to_display: bpy.props.EnumProperty(
        name="Dislay What",
        description="Choose what type of data to display",
        items = [
            ("asset", "asset", "asset"),
            ("search", "search", "search"),
            ("fav", "fav", "fav"),
            ("recent", "recent", "recent"),
            ("preset", "preset", "preset")
        ],
        default = "asset"
    )

    category_order_list: bpy.props.CollectionProperty(type=NMSCategoryOrderItem)
    category_order_list_index: bpy.props.IntProperty()

    # Rows for the main panel's category list, kept in step with the categories enum.
    # Picking a row selects a category (on_category_list_index_changed).
    category_list: bpy.props.CollectionProperty(type=NMSCategoryOrderItem)
    category_list_index: bpy.props.IntProperty(
        update=lambda self, context: self.on_category_list_index_changed(),
    )

    favourite_categories = []
    favourite_objects_data = {}
    recent_objects_data = {}
    presets_data = {}

    categories_data = {}
    search_results = {}
    # Sub category enum entries per category; the same list is returned each time
    # so Blender's dynamic enum strings stay alive.
    sub_categories_by_category = {}

    def initialise_asset_browser(self):
        self.get_categories_data()
        self.refresh_categories()

        AssetBrowser.sub_categories_by_category.clear()

        AssetBrowser.presets_data = self.get_presets_data()
        AssetBrowser.enum_sub_categories = self.extract_enum_sub_categories()

        if self.enum_asset_browser_what_to_display == "search":
            search_text = self.asset_broser_search_query
            search_results = self.filter_objects_with_string(search_text)
            AssetBrowser.search_results = search_results

    def refresh_categories(self):
        """Rebuild the category enum, favourites first in their saved order.
        Rebuilt in place, as the class attribute outlives unregister."""
        categories_data = self.get_categories_data()
        favourite_categories = self.get_favourite_categories()
        ordered_categories = asset_browser_utils.order_categories(
            categories_data.keys(), favourite_categories
        )
        AssetBrowser.enum_categories[:] = asset_browser_utils.build_enum_entries(
            ordered_categories
        )

        # Always via the timer: this can run while Blender draws, where a scene
        # collection can't be written to.
        self.request_category_list_refresh()

    def refresh_category_list(self):
        """Rebuild the main panel's category rows; only called from the timer.
        Favourites, Recents and Presets come first, then a spacer, then the categories."""
        favourite_categories = self.get_favourite_categories()

        self.category_list.clear()

        for row_kind, label, icon in SPECIAL_LIST_ROWS:
            item = self.category_list.add()
            item.row_kind = row_kind
            item.category_name = label

        spacer = self.category_list.add()
        spacer.row_kind = "spacer"

        for category_element in AssetBrowser.enum_categories:
            category = category_element[0]
            item = self.category_list.add()
            item.category_name = category
            item.is_fav = category in favourite_categories

        # keep the highlighted row on whatever category is actually selected,
        # since a favourite toggle or a reorder moves the rows around
        self.sync_category_list_index()

    def request_category_list_refresh(self):
        """Queue refresh_category_list on a timer, since it can't run from a draw()."""
        if bpy.app.timers.is_registered(_refresh_category_list):
            return
        bpy.app.timers.register(_refresh_category_list, first_interval=0.0)

    def sync_category_list_index(self):
        """Highlight the row for what the panel shows: Favourites, Recents,
        Presets, or else the selected category."""
        display_what = self.enum_asset_browser_what_to_display

        for index, item in enumerate(self.category_list):
            if item.row_kind == "spacer":
                continue

            if item.row_kind == "category":
                # a category row only matches while a category is on show,
                # otherwise "fav"/"recent"/"preset" is what to look for
                matches = (
                    display_what not in ("fav", "recent", "preset")
                    and item.category_name == self.asset_browser_caterogies
                )
            else:
                matches = item.row_kind == display_what

            if matches:
                if self.category_list_index != index:
                    self.category_list_index = index
                return

    def on_category_list_index_changed(self):
        """Act on the clicked row: select a category or switch the view.
        The spacer row does nothing."""
        index = self.category_list_index
        if not (0 <= index < len(self.category_list)):
            return

        item = self.category_list[index]
        if item.row_kind == "category":
            if item.category_name != self.asset_browser_caterogies:
                self.asset_browser_caterogies = item.category_name
            else:
                # Same category, so on_category_selected won't fire on its own;
                # call it to leave the special view.
                self.on_category_selected()
        elif item.row_kind == "fav":
            self.show_favourite_obejcts()
        elif item.row_kind == "recent":
            self.show_recent_objects()
        elif item.row_kind == "preset":
            self.show_presets()


    def get_grid_size_prop_string(self):
        return asset_browser_utils.get_grid_size_properties(
            self.enum_asset_browser_mode
        )


    def get_grid_sizes(self):
        """Icon size and column count for the current view mode, from the addon preferences."""
        icon_size_prop, number_of_columns_prop = self.get_grid_size_prop_string()
        return asset_browser_utils.get_grid_settings(
            bpy.context, icon_size_prop, number_of_columns_prop
        )


    def get_categories(self):
        if not AssetBrowser.enum_categories:
            self.initialise_asset_browser()
        return AssetBrowser.enum_categories

    def on_category_selected(self):
        self.enum_asset_browser_what_to_display = "asset"
        AssetBrowser.enum_sub_categories = self.extract_enum_sub_categories()
        self.asset_browser_sub_caterogies = "All"


    def on_sub_category_selected(self):
        self.enum_asset_browser_what_to_display = "asset"
        AssetBrowser.enum_sub_categories = self.extract_enum_sub_categories()

    def get_enum_sub_categories(self):
        return self.extract_enum_sub_categories()

    def extract_enum_sub_categories(self):
        """Sub category enum entries for the selected category.
        Runs on every redraw, so it uses the cached list."""
        prop_caterogies = self.asset_browser_caterogies

        cached = AssetBrowser.sub_categories_by_category.get(prop_caterogies)
        if cached is not None:
            return cached

        sub_categories = asset_browser_utils.build_sub_category_entries(
            self.get_categories_data(), prop_caterogies
        )

        AssetBrowser.sub_categories_by_category[prop_caterogies] = sub_categories
        return sub_categories

    def get_categories_data(self):
        if not AssetBrowser.categories_data:
            AssetBrowser.categories_data = self.get_category_vise_objects()
            self.set_favourite_objects(
                asset_browser_utils.load_stored_list("favourite_objects")
            )
            self.set_recent_objects(
                asset_browser_utils.load_stored_list("recent_objects")
            )

        return AssetBrowser.categories_data

    def get_enum_categories_list(self):
        return AssetBrowser.enum_categories

    def get_enum_sub_categories_list(self):
            return AssetBrowser.enum_sub_categories

    def on_search_entered(self):
        search_filter = self.asset_broser_search_query
        if search_filter and len(search_filter) > 2:
            self.check_display_search_results = True
            self.enum_asset_browser_what_to_display = "search"
            search_results = self.filter_objects_with_string(search_filter)
            AssetBrowser.search_results = search_results
        else:
            self.check_display_search_results = False
            self.enum_asset_browser_what_to_display = "asset"
            AssetBrowser.search_results = {}

    def filter_objects_with_string(self,search_filter):
        return asset_browser_utils.filter_objects(
            self.get_categories_data(), search_filter
        )

    def get_search_results(self):
        return AssetBrowser.search_results

    # (query, results, total) of the header menu's last search
    _quick_search_cache = (None, {}, 0)

    def get_quick_search_results(self, limit=8):
        """The header menu's search results: ({object id: part data}, match count).
        Only recomputed when the query changes."""
        query = self.quick_search_query.strip()
        cached_query, results, total = AssetBrowser._quick_search_cache
        if query != cached_query:
            results, total = asset_browser_utils.quick_search(
                self.get_categories_data(), query, limit
            )
            AssetBrowser._quick_search_cache = (query, results, total)
        return results, total


    def get_category_vise_objects(self):
        return asset_browser_utils.build_category_tree()

    def set_favourite_categories(self, favourite_categories):
        AssetBrowser.favourite_categories = favourite_categories
        self.refresh_categories()
        # Cheap enough to always keep in sync, so the reorder popup reflects a
        # favourite toggled from either the popup itself or the main panel.
        self.refresh_category_order_list()

    def get_favourite_categories(self, context = None):
        # the default used to be bpy.context itself, which binds whatever context
        # happened to exist at import time rather than the live one
        if not AssetBrowser.favourite_categories:
            AssetBrowser.favourite_categories = (
                asset_browser_utils.load_stored_list("favourite_categories")
            )
        return AssetBrowser.favourite_categories

    def refresh_category_order_list(self):
        """Rebuild the reorder list rows from the current category order."""
        favourite_categories = self.get_favourite_categories()
        self.category_order_list.clear()
        for category_element in AssetBrowser.enum_categories:
            category = category_element[0]
            item = self.category_order_list.add()
            item.category_name = category
            item.is_fav = category in favourite_categories

    def move_category(self, category, direction):
        categories_data = self.get_categories_data()
        favourite_categories = self.get_favourite_categories()
        asset_browser_utils.move_category(
            categories_data.keys(), favourite_categories, category, direction
        )
        self.refresh_categories()
        self.refresh_category_order_list()

    def set_favourite_objects(self, new_favourite_objects):
        AssetBrowser.favourite_objects_data = asset_browser_utils.apply_favourites(
            self.get_categories_data(), new_favourite_objects
        )


    def get_favourite_objects_data(self):
        # the favourites are read in with the part tree - loading it here
        # means the header menu has them before anything else has asked
        self.get_categories_data()
        return AssetBrowser.favourite_objects_data

    def show_favourite_obejcts(self):
        self.enum_asset_browser_what_to_display = "fav"
        # the row is already highlighted when this came from clicking it,
        # but not when the view was switched some other way
        self.sync_category_list_index()


    def set_recent_objects(self, new_recent_objects):
        AssetBrowser.recent_objects_data = (
            asset_browser_utils.collect_recent_objects(
                self.get_categories_data(), new_recent_objects
            )
        )

    def get_recent_objects_data(self):
        # read in with the part tree, like the favourites
        self.get_categories_data()
        return AssetBrowser.recent_objects_data

    def show_recent_objects(self):
            self.enum_asset_browser_what_to_display = "recent"
            self.sync_category_list_index()

    def add_to_recents_list(self, object_id):
        recent_objs = asset_browser_utils.push_recent(
            asset_browser_utils.load_stored_list("recent_objects"), object_id
        )
        asset_browser_utils.save_stored_list("recent_objects", recent_objs)
        self.set_recent_objects(recent_objs)

    def get_presets_data(self):
        return asset_browser_utils.build_presets_data()

    def show_presets(self):
        self.enum_asset_browser_what_to_display = "preset"
        self.sync_category_list_index()

    def get_preset_data(self):
        return AssetBrowser.presets_data


classes = (
    NMSCategoryOrderItem,
    AssetBrowser,
) + asset_browser_operators.classes + asset_browser_presentation.classes


def register():
    for _class in classes:
        bpy.utils.register_class(_class)
    bpy.types.Scene.nms_asset_browser = bpy.props.PointerProperty(type=AssetBrowser)


def unregister():
    del bpy.types.Scene.nms_asset_browser
    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)
