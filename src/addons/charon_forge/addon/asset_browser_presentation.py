import bpy
import json
from ..utils import icon_utils
from ..utils import asset_browser_utils
from ..utils.asset_browser_utils import (get_grid_settings, get_preferences,
                                         resolve_sub_categories)
ADDON_ID = asset_browser_utils.ADDON_ID

OP_OBJECT_SELECTED = "object.nms_asset_browser_object_selected"
OP_MORE_OPTIONS = "object.nms_asset_browser_more_options"

# How tall the main panel's category list is before it starts scrolling.
CATEGORY_LIST_ROWS = 25


def draw_sub_category(pcoll , container, label, elements_list, number_of_columns, icon_size, grid_type = "Grid", show_title = True ):
            
    sub_category_column = container.column(align = True)
    sub_cat_label_row = sub_category_column.row()
    
    if show_title:
        sub_cat_label_row.label(text = label)
    
    subcategory_row = None

    for index,(obj_id,part_data) in enumerate(elements_list.items()):
        asset_icon_id = pcoll[obj_id].icon_id if obj_id in pcoll else None
        if index%number_of_columns == 0:
            subcategory_row = sub_category_column.row(align = True)
        
        drawing_function = draw_list_element if grid_type == "List" else draw_grid_element
        drawing_function(
            grid = subcategory_row,
            grid_icon_size = icon_size,
            object_id = obj_id,
            part_data = part_data,
            asset_icon_value = asset_icon_id,
        )
        
    remaining_rows = number_of_columns - len(elements_list)%number_of_columns
    if subcategory_row and remaining_rows != number_of_columns:
        for _ in range(remaining_rows):
            subcategory_row.column(align = True).label(text = "")

def draw_grid_element( 
        grid, 
        grid_icon_size, 
        object_id,
        part_data,
        asset_icon_value = None, 
    ):
    
    asset_name = part_data["name"]
    variants = part_data.get("variants",None)
    is_fav = part_data.get("is_fav",False)
    is_preset = part_data.get("is_preset",False)
    
    if not asset_name:
        return
    
    asset_column = grid.box().column(align=True)
    asset_icon_row = asset_column.row(align = True)
    asset_icon_col = asset_icon_row.column(align = True)
    asset_icon_col.scale_x = 2.0
    try:
        asset_icon_col.template_icon( icon_value = asset_icon_value, scale = grid_icon_size)
    except:
        enum_items = bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items["MONKEY"].value
        asset_icon_col.template_icon( icon_value = enum_items,scale= grid_icon_size)
        
    action_butons_column = asset_icon_row.column(align = False)
    add_button = action_butons_column.operator( OP_OBJECT_SELECTED,  text = "",  emboss = True,  icon ="ADD" )
    add_button.object_id = object_id
    add_button.is_preset = is_preset
    
    if not is_preset:
        draw_more_options_button(action_butons_column, object_id, is_fav, variants)

    # the name adds the part itself too - its variants are in the options
    # popup, under the button below the +
    asset_column_text_row = asset_column.row(align = False)
    button = asset_column_text_row.operator(OP_OBJECT_SELECTED, text = asset_name, emboss = False)
    button.object_id = object_id
    button.is_preset = is_preset


def draw_more_options_button(layout, object_id, is_fav, variants, emboss=False):
    """The button that opens a part's options popup - favourite, replace,
    and its variants when it has any."""
    more_options_button = layout.operator(
        OP_MORE_OPTIONS, text = "", emboss = emboss, icon = "COLLAPSEMENU"
    )
    more_options_button.object_id = object_id
    more_options_button.is_fav = is_fav
    # the whole family, the main part first, so the popup lists every form
    more_options_button.variants = (
        json.dumps([object_id] + [v for v in variants if v != object_id])
        if variants else ""
    )
    
    
def draw_list_element( 
        grid, 
        grid_icon_size, 
        object_id, 
        part_data,
        asset_icon_value = None, 
    ):
    
    
    asset_name = part_data["name"]
    variants = part_data.get("variants",None)
    is_fav = part_data.get("is_fav",False)
    is_preset = part_data.get("is_preset",False)
    
    element_row = grid.box().row(align = True)
    element_icon_row = element_row.row(align = True)
    element_icon_row.scale_x = 1.8
    try:
        element_icon_row.template_icon( icon_value = asset_icon_value, scale = grid_icon_size)
    except:
        enum_items = bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items["MONKEY"].value
        element_icon_row.template_icon( icon_value = enum_items,scale= grid_icon_size)
    
    if grid_icon_size == 1:
        element_row_right = element_row.row(align = True)
        element_row_right.label(text = asset_name)
        add_button_row = element_row_right.row(align = True)
        add_button_2 = add_button_row.operator(OP_OBJECT_SELECTED, text = "", emboss = True, icon = "ADD")
        
    else:
        element_row_right = element_row.column(align = True)
        element_row_right.label(text = asset_name)
        for _ in range(grid_icon_size-2):
            element_row_right.label(text = "")
        add_button_row = element_row_right.row(align = True)
        add_button_row.label(text = "")
        add_button_2 = add_button_row.operator(OP_OBJECT_SELECTED, text = "", emboss = True, icon = "ADD")
        
    add_button_2.object_id = object_id
    add_button_2.is_preset = is_preset
    # variants, favourite and replace are in the options popup, as in the grid
    if not is_preset:
        draw_more_options_button(add_button_row, object_id, is_fav, variants, emboss=True)
    


def draw_asset_browser(context, asset_browser_box, scene):
    
    asset_browser = scene.nms_asset_browser
    grid_type = asset_browser.enum_asset_browser_mode
    
    ab_category = asset_browser.asset_browser_caterogies
    ab_sub_category = asset_browser.asset_browser_sub_caterogies
    
    if grid_type == "List":
        icon_size, number_of_columns = get_grid_settings(
            context, "asset_browser_icon_size_list",
            "asset_browser_number_of_columns_list")
    else:
        icon_size, number_of_columns = get_grid_settings(
            context, "asset_browser_icon_size",
            "asset_browser_number_of_columns")
    
    
    show_serch_results = asset_browser.check_display_search_results
    
    pcoll = icon_utils.get_asset_icons_pcoll()
    categories_data = asset_browser.get_categories_data()
    
    search_row = asset_browser_box.row(align=True)
    search_row.prop(asset_browser, "asset_broser_search_query", text="", icon='VIEWZOOM')
    search_row.separator()
    grid_options_row = search_row.row(align = True)
    grid_options_row.scale_x = 0.3
    grid_options_row.prop(asset_browser,"enum_asset_browser_mode", text = "View type", expand = True)
    setting_button = search_row.operator("object.nms_asset_browser_list_settings", icon = "SETTINGS", text = "")
    setting_button.grid_type = grid_type
    
    if grid_type == "Other":
        main_split = asset_browser_box.split(factor=0.13)
        left_col = main_split.column(align=True)
        right_box = main_split.column(align = True)
        
        left_col.label(text = "Asset Browser", icon='ASSET_MANAGER')
        left_col.separator()
        
        categories_col = left_col.column(align = True)
        categories_col.enabled = not asset_browser.check_display_search_results
        categories_col.label(text="Categories" )
        categories_col.prop(asset_browser,"asset_browser_caterogies", expand = True)
        categories_col.scale_y = 1.5
        
    else:
        right_box = asset_browser_box.column(align = True)
    
    right_box.separator()
    top_category_row = right_box.row(align = True)
    
    if show_serch_results:
        sub_cat_dict = asset_browser.get_search_results()
    else:
        sub_cat_dict = resolve_sub_categories(
            categories_data, ab_category, ab_sub_category)
    
    if show_serch_results:
        right_box.separator()
        result_row = right_box.row(align = True)
        if sub_cat_dict:
            result_row.alert = False
            result_row.label(text = f"Showing search results ( {len(sub_cat_dict)} found ) ...")
        else:
            result_row.alert = True
            result_row.label(text = f"No matching parts found")
    else:
        if grid_type == "Grid":
            top_category_column = top_category_row.column(align = True)
            top_category_column.label(text = "Categories")
            cats_per_row = 4
            cat_row = None
            for index, category_element in enumerate(asset_browser.get_enum_categories_list()):
                category = category_element[0]
                if index % cats_per_row == 0:
                    cat_row = top_category_column.row(align = True)
                cat_button = cat_row.operator(
                    "object.nms_asset_browser_category_selected",
                    text = category,
                    depress = category == ab_category
                )
                cat_button.category = category
            remaining_rows = cats_per_row - len(categories_data)%cats_per_row
            if cat_row and remaining_rows != cats_per_row:
                for _ in range(remaining_rows):
                    cat_row.column(align = True).label(text = "")
            
            top_category_column.separator()
            top_category_column.label(text = "Sub-Categories")
            cat_row = None
            sub_cats_enum = asset_browser.get_enum_sub_categories_list()
            for index, sub_cat in enumerate(sub_cats_enum):
                sub_category = sub_cat[0]
                if index % cats_per_row == 0:
                    cat_row = top_category_column.row(align = True)
                cat_button = cat_row.operator(
                    "object.nms_asset_browser_sub_category_selected",
                    text = sub_category,
                    depress = sub_category == ab_sub_category
                )
                cat_button.sub_category = sub_category
            remaining_rows = cats_per_row - len(sub_cats_enum)%cats_per_row
            if cat_row and remaining_rows != cats_per_row:
                for _ in range(remaining_rows):
                    cat_row.column(align = True).label(text = "")
        elif grid_type == "List":
            top_category_column = top_category_row.column(align = True)
            top_category_column.label(text = "Category")
            top_categories_row = top_category_column.row(align = True)
            top_categories_row.prop(asset_browser,"asset_browser_caterogies", expand = False, text = "" ) 
            sub_category_column = top_category_row.column(align = True)
            sub_category_column.label(text = "Sub-Category")
            sub_categories_row = sub_category_column.row(align = True)
            sub_categories_row.prop( asset_browser, "asset_browser_sub_caterogies", expand = False, text = "" )

    
    for subcategories, object_ids in sub_cat_dict.items():
        right_box.separator()
        draw_sub_category(
            pcoll = pcoll, 
            container = right_box, 
            label = subcategories,
            elements_list = object_ids, 
            number_of_columns = number_of_columns,
            icon_size = icon_size,
            grid_type = grid_type
        )
        

class NMS_UL_asset_browser_category_order(bpy.types.UIList):
    """Rows for reordering categories, with an up/down button per row.

    Favourites and non-favourites are kept in separate contiguous blocks by
    AssetBrowser.move_category, so a plain up/down swap here can never let a
    row cross into the other block - see asset_browser_utils.move_category.
    """

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.category_name)

        controls_row = row.row(align=True)
        controls_row.alignment = "RIGHT"

        fav_button = controls_row.operator(
            "object.nms_asset_browser_category_favourite",
            text="",
            icon="PINNED" if item.is_fav else "UNPINNED",
            emboss=False,
        )
        fav_button.category = item.category_name

        controls_row.separator()

        up_button = controls_row.operator(
            "object.nms_asset_browser_category_move", text="", icon="TRIA_UP", emboss=False
        )
        up_button.category = item.category_name
        up_button.direction = "UP"
        down_button = controls_row.operator(
            "object.nms_asset_browser_category_move", text="", icon="TRIA_DOWN", emboss=False
        )
        down_button.category = item.category_name
        down_button.direction = "DOWN"
        
        
# row_kind -> (icon, description) for the special rows at the top of the
# list - see AssetBrowser.SPECIAL_LIST_ROWS.
SPECIAL_ROW_ICONS = {
    "fav": "FUND",
    "recent": "RECOVER_LAST",
    "preset": "ASSET_MANAGER",
}

# How thin the rule between list rows is. Blender has no divider of its own,
# so an empty box squashed on the y axis stands in for one - a box is the
# only thing that paints a border, and with nothing in it all that is left
# is the border itself.
ROW_RULE_SCALE_Y = 0.06



class NMS_UL_asset_browser_category(bpy.types.UIList):
    """Rows for the main panel's category list.

    Three kinds of row share this list - see AssetBrowser.refresh_category_list:
    a plain category (with a pin button), one of the three special views
    (Favourite/Recent/Preset Items), or a blank spacer row separating the
    two groups. Selecting a row is what activates it - the list's own index
    drives it, see AssetBrowser.on_category_list_index_changed - so names
    are plain labels rather than operator buttons.
    """

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if item.row_kind == "spacer":
            # deliberately empty - just the gap between the special rows and
            # the ordinary categories below them
            layout.separator()
            return

        asset_browser = data

        if item.row_kind != "category":
            cell = layout.column(align=True)
            cell.label(
                text=item.category_name,
                icon=SPECIAL_ROW_ICONS.get(item.row_kind, "BLANK1"),
            )
            return

        is_active = item.category_name == asset_browser.asset_browser_caterogies
        display_what = asset_browser.enum_asset_browser_what_to_display
        is_expanded = is_active and display_what == "asset"

        # everything for this row goes in one column, so the selected row's
        # highlight covers the sub categories too rather than just the name
        cell = layout.column(align=True)

        row = cell.row(align=True)
        row.label(text=item.category_name)

        controls_row = row.row(align=True)
        controls_row.alignment = "RIGHT"
        fav_button = controls_row.operator(
            "object.nms_asset_browser_category_favourite",
            text="",
            icon="PINNED" if item.is_fav else "UNPINNED",
            emboss=False,
        )
        fav_button.category = item.category_name

        if is_expanded:
            # a row can be taller than the rest - see NMS_UL_actions_list in the
            # base builder addon, which draws a whole grid of buttons in one
            sub_cat_col = cell.column(align=True)
            sub_cat_col.scale_y = 0.8
            for sub_cat in asset_browser.get_enum_sub_categories_list():
                sub_category = sub_cat[0]
                is_sub_active = sub_category == asset_browser.asset_browser_sub_caterogies

                button_row = sub_cat_col.row(align=True)
                button_row.alignment = "LEFT"
                sub_cat_button = button_row.operator(
                    "object.nms_asset_browser_sub_category_selected",
                    text=sub_category,
                    depress=is_sub_active,
                    emboss=False,
                    icon="TRIA_RIGHT" if is_sub_active else "BLANK1",
                )
                sub_cat_button.sub_category = sub_category
            #rule = cell.row(align = True)
            #rule.scale_y = 0.3
            #rule.label(text = ".................................................................")
            #rule.separator()
        #.separator(factor = 1)


def draw_asset_browser_left_options(context, asset_browser_box, scene):
    asset_browser = scene.nms_asset_browser
    prefs = get_preferences(context)

    search_column= asset_browser_box.column(align=True)
    search_column.scale_y = 1.4
    search_column.label(text = "Search")
    search_column.prop(asset_browser, "asset_broser_search_query", text="", icon='VIEWZOOM')

    asset_browser_box.separator()
    if prefs is not None:
        size_column = asset_browser_box.column(align = True)
        size_column.prop(prefs, "asset_browser_icon_size_other",text = "Icon Size")
        size_column.prop(prefs, "asset_browser_number_of_columns_other", text = "Columns")
    asset_browser_box.separator()

    cats_col = asset_browser_box.column(align = True)
    cats_header_row = cats_col.row(align = True)
    cats_header_row.label(text="Categories" )
    reorder_row = cats_header_row.row(align = True)
    reorder_row.alignment = "RIGHT"
    reorder_row.operator( "object.nms_asset_browser_category_reorder_popup", text = "Reorder", icon = "SORTSIZE" )
    cats_col.separator()

    # the rows can first be asked for mid-draw, where they cannot be written
    asset_browser.request_category_list_refresh()

    categories_col = cats_col.column(align = True)
    categories_col.enabled = not asset_browser.check_display_search_results
    categories_col.template_list(
        "NMS_UL_asset_browser_category",
        "",
        asset_browser,
        "category_list",
        asset_browser,
        "category_list_index",
        rows = CATEGORY_LIST_ROWS,
    )



def draw_asset_browser_right_options(context,asset_browser_box, scene, grid_type = "Grid"):
    asset_browser = scene.nms_asset_browser
    
    ab_category = asset_browser.asset_browser_caterogies
    ab_sub_category = asset_browser.asset_browser_sub_caterogies
    
    icon_size, number_of_columns = get_grid_settings(
        context, "asset_browser_icon_size_other",
        "asset_browser_number_of_columns_other")
    show_serch_results = asset_browser.check_display_search_results
    
    display_what = asset_browser.enum_asset_browser_what_to_display
    
    pcoll = icon_utils.get_asset_icons_pcoll()
    categories_data = asset_browser.get_categories_data()
    
    
    if display_what == "search":
        sub_cat_dict = asset_browser.get_search_results()
    elif display_what == "fav":
        fav_data = asset_browser.get_favourite_objects_data()
        sub_cat_dict = {"Favourite Objects": fav_data}
    elif display_what == "recent":
        recent_data = asset_browser.get_recent_objects_data()
        sub_cat_dict = {"Recent Objects": recent_data}
    elif display_what == "preset":
        preset_data = asset_browser.get_preset_data()
        sub_cat_dict = {"Presets": preset_data}
    else:
        sub_cat_dict = resolve_sub_categories(
            categories_data, ab_category, ab_sub_category)
    
    for subcategories, object_ids in sub_cat_dict.items():
        asset_browser_box.separator()
        draw_sub_category(
            pcoll = pcoll, 
            container = asset_browser_box, 
            label = subcategories,
            elements_list = object_ids, 
            number_of_columns = number_of_columns,
            icon_size = icon_size,
            grid_type = grid_type
        )

class NMS_PT_asset_browser_panel(bpy.types.Panel):
    bl_label       = "Asset Browser"
    bl_idname      = "MY_PT_asset_browser_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NMS Asset Browser"
    bl_context = "objectmode"
    
    def draw(self, context):
        layout = self.layout     
        scene = context.scene
        draw_asset_browser(context,layout, scene)


class NMS_PT_asset_browser_properties_panel(bpy.types.Panel):
    bl_label       = "Asset Browser"
    bl_idname      = "MY_PT_asset_browser_properties_panel"
    bl_space_type  = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context     = 'modifier'
    bl_order       = 0 
    
    def draw(self, context):
        layout = self.layout     
        scene = context.scene
        draw_asset_browser_right_options(context, layout, scene)
        
        
class NMS_PT_asset_browser_new_window_panel_left(bpy.types.Panel):
    bl_label       = "Asset Browser"
    bl_idname      = "MY_PT_asset_browser_new_window_panel_left"
    bl_space_type  = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context     = 'constraint'
    bl_order       = 0 
    
    def draw(self, context):
        layout = self.layout     
        scene = context.scene
        draw_asset_browser_left_options(context, layout, scene)
        
classes = (
    NMS_UL_asset_browser_category_order,
    NMS_UL_asset_browser_category,
    
    NMS_PT_asset_browser_properties_panel,
    #NMS_PT_asset_browser_panel,
    NMS_PT_asset_browser_new_window_panel_left
)
        
