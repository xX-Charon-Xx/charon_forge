"""A builder the base builder addon will accept through its set_builder() hook.

That hook only takes subclasses of the addon's own Builder, and that class only
exists once the addon is loaded, so the subclass is made at runtime - the
addon's Builder with HighResBuilderMixin in front of it. Parts it places are
the addon's own Part classes, so its panels and operators keep working on them.

    host_builder = host.create_host_builder()
    base_builder_utils.set_builder(host_builder)
"""

from ..utils import base_builder_utils
from .mixin import HighResBuilderMixin

# one subclass per host Builder class, so isinstance checks against an earlier
# instance still hold. Keyed by the class itself - a reloaded addon brings a new
# Builder class and gets a new subclass.
_host_classes = {}


def create_host_builder_class(host_builder_class):
    """The host's Builder class with the high res library layered on.

    Args:
        host_builder_class (type): The base builder addon's Builder class, see
            base_builder_utils.get_builder_class().

    Returns:
        type: A subclass of host_builder_class.
    """
    host_class = _host_classes.get(host_builder_class)
    if host_class is None:
        host_class = type(
            "CharonHostBuilder",
            (HighResBuilderMixin, host_builder_class),
            {"__module__": __name__, "__doc__": __doc__},
        )
        _host_classes[host_builder_class] = host_class
    return host_class


def create_host_builder():
    """An instance ready for base_builder_utils.set_builder(), or None when
    the base builder addon isn't available."""
    host_builder_class = base_builder_utils.get_builder_class()
    if host_builder_class is None:
        return None
    return create_host_builder_class(host_builder_class)()
