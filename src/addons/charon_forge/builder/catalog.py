"""Lookup of the fbx part models and presets available on disk."""

import os

from ..nms import preset
from ..nms.utils import dictionary
from . import paths

# {object id: fbx path} for the base builder addon's model folder, built on
# first use. Kept out of part_reference and looked up lazily because a Builder
# can be constructed before that addon has finished registering, and a pack
# folded in at construction time would be missing for the rest of the session.
_host_fbx_index = None
_host_fbx_root = None


def _index_fbx_files(root):
    """{object id: full path} for a models folder of category subfolders."""
    index = {}
    for category in sorted(os.listdir(root)):
        category_path = os.path.join(root, category)
        if not os.path.isdir(category_path):
            continue
        for part_file in os.listdir(category_path):
            if part_file.endswith(".fbx"):
                index.setdefault(
                    os.path.splitext(part_file)[0],
                    os.path.join(category_path, part_file),
                )
    return index


def get_host_obj_path(part):
    """Where the base builder addon keeps the fbx for a part, if it has one.

    Charon Forge ships no fbx library of its own - see paths.MODEL_PATH - so
    without this every part would come back with no proxy to switch down to.
    """
    global _host_fbx_index, _host_fbx_root

    root = paths.get_host_model_path()
    if root is None:
        return None

    if _host_fbx_index is None or _host_fbx_root != root:
        _host_fbx_index = _index_fbx_files(root)
        _host_fbx_root = root

    return _host_fbx_index.get(part)


class Catalog(object):
    """What parts and presets exist, and where their files are.

    Knows nothing about the scene - the Builder that subclasses it does.
    """

    MODEL_PATH = paths.MODEL_PATH
    MODS_PATH = paths.MODS_PATH
    PRESET_PATH = paths.PRESET_PATH

    nice_name_dictionary = dictionary.get_nice_names_diictionary()

    def __init__(self):
        # Create default part pack.
        self.available_packs = [("Parts", self.MODEL_PATH)]

        # Find any mods with model packs inside.
        if os.path.exists(self.MODS_PATH):
            for mod_folder in os.listdir(self.MODS_PATH):
                full_mod_path = os.path.join(self.MODS_PATH, mod_folder)
                if "models" in os.listdir(full_mod_path):
                    full_model_path = os.path.join(full_mod_path, "models")
                    self.available_packs.append((mod_folder, full_model_path))

        # Find Parts and build a reference dictionary.
        self.part_reference = {}
        for pack_name, pack_folder in self.available_packs:
            search_path = pack_folder or self.MODEL_PATH
            for category in self.get_categories(pack=pack_name):
                for part_file in self.get_objs_from_category(category, pack=pack_name):
                    unique_id = os.path.splitext(part_file)[0]
                    self.part_reference[unique_id] = {
                        "category": category,
                        "full_path": os.path.join(search_path, category, part_file),
                        "pack": pack_name,
                    }

    # Parts ---
    def get_categories(self, pack=None):
        """Get the list of categories.

        Args:
            pack (str): The model pack search under for categories.
                Use this for mod support. Defaults to vanilla 'Parts'.
        Returns:
            list: List of folders underneath category path.
        """
        search_path = self.get_model_path_from_pack(pack or "Parts")
        return [
            item
            for item in os.listdir(search_path)
            if os.path.isdir(os.path.join(search_path, item))
        ]

    def get_objs_from_category(self, category, pack=None):
        """Get a list of parts belonging to a category.

        Args:
            category (str): The name of the category.
            pack (str): The model pack search under for categories.
                Use this for mod support. Defaults to vanilla 'Parts'.
        """
        search_path = self.get_model_path_from_pack(pack or "Parts")
        category_path = os.path.join(search_path, category)
        return sorted(
            part_file
            for part_file in os.listdir(category_path)
            if part_file.endswith(".fbx")
        )

    def get_parts_from_category(self, category, pack=None):
        """Get all the parts from a specific category.

        Args:
            category (str): The category to search.
            pack (str): The model pack name. Defaults to vanilla 'Parts'.
        """
        pack = pack or "Parts"
        return sorted(
            item
            for item, value in self.part_reference.items()
            if value["pack"] == pack and value["category"] == category
        )

    def get_obj_path(self, part):
        """Get the path to the fbx file of a part, None if there isn't one.

        Falls back to the base builder addon's library for anything our own
        model folder and the user's mod packs don't cover, which is almost
        everything - see get_host_obj_path.
        """
        entry = self.part_reference.get(part)
        if entry is not None:
            return entry["full_path"]
        return get_host_obj_path(part)

    def get_obj_parent_folder(self, part):
        """Get the category folder a part's fbx file sits in."""
        path = self.get_obj_path(part)
        return os.path.dirname(path).split(os.sep)[-1]

    def get_model_path_from_pack(self, pack_request):
        """Given a pack name, return it's associated path.

        Args:
            pack_request (str): The name of the pack

        Return:
            str: The model path of the pack.
        """
        for pack_name, pack_path in self.available_packs:
            if pack_name == pack_request:
                return pack_path

    def get_nice_name(self, part):
        """Get a nice version of the part id."""
        part = os.path.basename(part)
        nice_name = part.title().replace("_", " ")
        return self.nice_name_dictionary.get(part, nice_name)

    # Presets ---
    def get_preset_categories(self):
        """Get the list of preset categories.

        Returns:
            list: List of folders underneath preset path.
        """
        return [
            item
            for item in os.listdir(preset.Preset.PRESET_PATH)
            if os.path.isdir(os.path.join(preset.Preset.PRESET_PATH, item))
        ]

    def get_uncategorized_presets(self):
        return self._list_presets(preset.Preset.PRESET_PATH)

    def get_presets_from_category(self, category):
        """Get a list of presets underneath a category.

        Args:
            category (str): The name of the category.
        """
        return self._list_presets(os.path.join(preset.Preset.PRESET_PATH, category))

    @staticmethod
    def _list_presets(folder):
        return [
            os.path.splitext(preset_file)[0]
            for preset_file in os.listdir(folder)
            if preset_file.endswith((".json", ".nmsprefab"))
        ]
