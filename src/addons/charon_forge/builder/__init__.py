"""Charon Forge's part builder.

    paths.py          where things are on disk
    catalog.py        which fbx parts and presets exist
    asset_library.py  the high res library: which .blend holds which part, and
                      loading its mesh
    proxy_library.py  the fbx proxies, cached and coloured per UserData
    placement.py      turning those meshes into placed parts
    importer.py       building every part in a save at once
    builder.py        Builder - scene lookups, serialising, presets, rigs
    mixin.py          HighResBuilderMixin - the high res library layered onto
                      any builder class
    host.py           the same, onto the base builder addon's Builder, for its
                      set_builder() hook

Charon Forge's own tools use get_builder(). The functions below are the
module level entry points they call, and default to that builder.
"""

from . import asset_library, host, placement, proxy_library
from .builder import Builder
from .mixin import HighResBuilderMixin

__all__ = [
    "Builder",
    "CharonBuilder",
    "HighResBuilderMixin",
    "get_builder",
    "add_part",
    "deserialise_from_data",
    "load_high_res_mesh",
    "load_high_res_meshes",
    "new_high_res_object",
    "new_merge_source",
    "new_proxy_object",
    "apply_proxy_mesh",
    "create_host_builder",
    "create_host_builder_class",
]


class CharonBuilder(HighResBuilderMixin, Builder):
    """Charon Forge's builder: our Builder, placing parts from the high res library."""


_builder = None


def get_builder():
    """The builder shared by Charon Forge's own tools."""
    global _builder
    if _builder is None:
        _builder = CharonBuilder()
    return _builder


def add_part(object_id, user_data=None, build_rigs=True, high_res=True, builder_object=None):
    """Add a single part, from the high res library when it has one.

    Args:
        builder_object: The builder the part belongs to, so its part cache is
            the one that gets filled. Defaults to get_builder().
    """
    return placement.add_part(
        builder_object or get_builder(),
        object_id,
        user_data=user_data,
        build_rigs=build_rigs,
        high_res=high_res,
    )


def deserialise_from_data(data, builder_object=None):
    """Rebuild a base from NMS data."""
    return (builder_object or get_builder()).deserialise_from_data(data)


load_high_res_mesh = asset_library.load_high_res_mesh
load_high_res_meshes = asset_library.load_high_res_meshes
new_high_res_object = placement.new_high_res_object
new_merge_source = placement.new_merge_source
new_proxy_object = proxy_library.new_proxy_object
apply_proxy_mesh = proxy_library.apply_proxy_mesh

create_host_builder = host.create_host_builder
create_host_builder_class = host.create_host_builder_class
