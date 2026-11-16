"""A builder the base builder addon will accept through its set_builder() hook.
Made at runtime: the addon's Builder with HighResBuilderMixin in front."""

from ..utils import base_builder_utils
from .mixin import HighResBuilderMixin

# one subclass per host Builder class (a reloaded addon gets a new one)
_host_classes = {}


def create_host_builder_class(host_builder_class):
    """The host's Builder class with the high res library layered on."""
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
