"""Stand-ins for the base builder addon's helper modules.

Charon Forge uses that addon's blend_utils, python, userdata and overrides
modules in place when it is installed (see base_builder_utils). These are
what the same calls go to when it is not, so Charon Forge keeps working on
its own. They cover only what Charon Forge calls, and behave the same way.
"""
