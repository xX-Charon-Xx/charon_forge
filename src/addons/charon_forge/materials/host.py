"""Builds a material provider the base builder addon accepts through set_material_provider():
its own MaterialProvider with HighResMaterialsMixin in front, made at runtime."""

from ..utils import base_builder_utils
from .mixin import HighResMaterialsMixin

# one subclass per host MaterialProvider class, so isinstance checks still hold;
# a reloaded addon gets a new one
_host_classes = {}


def create_host_material_provider_class(host_provider_class):
    """The host's MaterialProvider class with high res colouring layered on."""
    host_class = _host_classes.get(host_provider_class)
    if host_class is None:
        host_class = type(
            "CharonHostMaterials",
            (HighResMaterialsMixin, host_provider_class),
            {"__module__": __name__, "__doc__": __doc__},
        )
        _host_classes[host_provider_class] = host_class
    return host_class


def create_host_material_provider():
    """An instance ready for base_builder_utils.set_material_provider(), or
    None when the base builder addon isn't available."""
    host_provider_class = base_builder_utils.get_material_provider_class()
    if host_provider_class is None:
        return None
    return create_host_material_provider_class(host_provider_class)()
