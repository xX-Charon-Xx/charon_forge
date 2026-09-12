"""A material provider the base builder addon will accept through its
set_material_provider() hook.

That hook only takes subclasses of the addon's own MaterialProvider, and that
class only exists once the addon is loaded, so the subclass is made at
runtime - the addon's MaterialProvider with HighResMaterialsMixin in front of
it. Flat parts keep being painted the addon's own way.

    host_materials = host.create_host_material_provider()
    base_builder_utils.set_material_provider(host_materials)
"""

from ..utils import base_builder_utils
from .mixin import HighResMaterialsMixin

# one subclass per host MaterialProvider class, so isinstance checks against an
# earlier instance still hold. A reloaded addon brings a new class and gets a
# new subclass.
_host_classes = {}


def create_host_material_provider_class(host_provider_class):
    """The host's MaterialProvider class with high res colouring layered on.

    Args:
        host_provider_class (type): The base builder addon's MaterialProvider,
            see base_builder_utils.get_material_provider_class().

    Returns:
        type: A subclass of host_provider_class.
    """
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
