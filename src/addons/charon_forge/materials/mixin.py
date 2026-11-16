"""HighResMaterialsMixin: sends colour calls for high res parts to colouring.py and
leaves the rest to the provider it's mixed into (ours in flat.py, or the host's)."""

from . import colouring


class HighResMaterialsMixin(object):

    def set_material(self, item, material):
        """Set a flat material and mirror its colour onto the object,
        so it reads the same in Object colour solid shading."""
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
        # High res parts keep their textures and get the game's own default
        # palette and finish, whatever `index` the host passed.
        if colouring.is_high_res(item):
            colouring.recolour_from_user_data(
                [item], colouring.default_user_data(colouring.object_id_of(item)))
            return None
        return super(HighResMaterialsMixin, self).assign_default_material(item, index=index)
