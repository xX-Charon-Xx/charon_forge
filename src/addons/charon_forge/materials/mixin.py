"""High res colouring, layered onto a material provider class.

HighResMaterialsMixin sends the colour calls for high res parts to the object
property colour system (colouring.py), and leaves every other part to the
provider it is mixed into. It relies only on the methods every provider has,
so it goes in front of either:

    class CharonMaterials(HighResMaterialsMixin, MaterialProvider)  # ours, flat.py
    type(..., (HighResMaterialsMixin, HostMaterialProvider), {})    # the base builder
                                                                   # addon's, host.py

The second is what makes it possible to hand our materials to the base builder
addon through its set_material_provider() hook - that hook only accepts
subclasses of its own MaterialProvider class.
"""

from . import colouring


class HighResMaterialsMixin(object):

    def set_material(self, item, material):
        """Set a flat material, and mirror its colour onto the object.

        Solid shading has to be set to Object colour for high res parts to be
        told apart - their materials are shared, so only the object can carry a
        per part viewport colour - and a flat part has to read the same under
        it, or half the scene goes white. See
        colouring.use_object_colour_in_viewport.
        """
        material = super(HighResMaterialsMixin, self).set_material(item, material)
        if material is not None:
            item.color = material.diffuse_color
        return material

    def restore_material(self, item, user_data_value):
        # High res parts colour by object property, so the value goes on
        # wholesale and their mesh keeps being shared.
        if colouring.is_high_res(item):
            try:
                user_data_value = int(user_data_value)
            except (TypeError, ValueError):
                return
            colouring.recolour_from_user_data([item], user_data_value)
            return
        return super(HighResMaterialsMixin, self).restore_material(item, user_data_value)

    def assign_material(self, item, colour_index=0, material_index=0):
        # A high res part is repainted in place instead - no flat material is
        # put over its textures, and nothing is copied.
        if colouring.is_high_res(item):
            colouring.recolour(
                [item], colour_index=colour_index, material_index=material_index
            )
            return None
        return super(HighResMaterialsMixin, self).assign_material(
            item, colour_index, material_index
        )

    def assign_default_material(self, item, index=0):
        # High res parts keep their real textures - painting the default grey
        # over them would throw the model away. Their equivalent is palette
        # `index`.
        if colouring.is_high_res(item):
            colouring.recolour_from_user_data([item], index)
            return None
        return super(HighResMaterialsMixin, self).assign_default_material(item, index=index)
