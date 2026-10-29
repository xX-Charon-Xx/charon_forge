"""Run with Blender --background --factory-startup --python-exit-code 1
--python tests/wing_mirror_regression.py -- --host-addon /path/to/no_mans_sky_base_builder.
Uses a temporary factory scene; does not save files or preferences.
"""
import argparse
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser()
parser.add_argument('--host-addon', required=True, type=Path)
parser.add_argument('--charon-addon', type=Path, help='Test an installed Charon copy instead of the source tree')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
repo = Path(__file__).resolve().parents[1]
charon_root = args.charon_addon or repo / 'src/addons/charon_forge'
sys.path[:0] = [str(charon_root.parent), str(args.host_addon.parent)]

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector
from mathutils.kdtree import KDTree
import no_mans_sky_base_builder as host
import charon_forge as charon
from charon_forge.builder import asset_library, mirror_fit
from charon_forge.builder.host import create_host_builder_class
from charon_forge.objects.part import Part
from charon_forge import host_patches
from no_mans_sky_base_builder.tools.build_tool import BuildTool
from no_mans_sky_base_builder.group import Group
from no_mans_sky_base_builder.utils import blend_utils, mirror_utils

# Expected pairs are catalog facts, independent of the lookup implementation.
ROOTS = ['B_WNG_' + letter for letter in 'ABCDEFGHIJKLMN'] + [
    'B_WNG_O_0', 'B_WNG_O_1', 'B_WNG_O_2', 'B_WNG_P', 'B_WNG_Q', 'B_WNG_R'] + [
    'B_WNG_' + letter for letter in 'STUVWXY']
PAIRS = {root: root + '_R' for root in ROOTS}
PAIRS.update({right: left for left, right in list(PAIRS.items())})
UNPAIRED = {'B_WNG_' + letter + mount for letter in 'PRWXY' for mount in ('_T', '_B')}
CATALOG = json.loads((charon_root / 'resources/nice_names.json').read_text())


def matrix_error(a, b):
    return max(abs(a[row][col] - b[row][col]) for row in range(4) for col in range(4))


def coords(mesh):
    points = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get('co', points)
    return points.reshape(-1, 3)


def surface_error(source, twin, fit):
    """Bidirectional sampled vertex error relative to the source's X mirror."""
    target = coords(source) * (-1, 1, 1)
    transform = np.array(fit)
    moved = coords(twin) @ transform[:3, :3].T + transform[:3, 3]
    def distance(a, b):
        tree = KDTree(len(b))
        for index, point in enumerate(b):
            tree.insert(point, index)
        tree.balance()
        return np.mean([tree.find(point)[2] for point in a[::max(1, len(a) // 1000)]])
    return max(distance(target, moved), distance(moved, target))


class WingMirrorTests(unittest.TestCase):
    def test_catalog_and_all_wing_ids(self):
        self.assertEqual({key for key in CATALOG if key.startswith('B_WNG_')}, set(PAIRS) | UNPAIRED)
        # The host's own lookup and catalog are only asked about the wings it
        # lists; newer ones reach it through host_patches, tested below.
        host_catalog = json.loads((args.host_addon / 'resources/nice_names.json').read_text())
        for part_class in (Part, host.part.Part):
            host_only = part_class is host.part.Part
            for source, twin in PAIRS.items():
                if host_only and source not in host_catalog:
                    continue
                with self.subTest(plugin=part_class.__module__, source=source):
                    self.assertEqual(part_class.get_mirror_part_id(source), twin)
                    self.assertIn(twin, CATALOG)
                    if host_only:
                        self.assertIn(twin, host_catalog)
                    self.assertTrue((charon_root / ('asset_browser/assets/' + twin + '.blend')).is_file())
                    self.assertEqual(part_class.get_mirror_part_id(twin), source)
            for source in UNPAIRED:
                if host_only and source not in host_catalog:
                    continue
                self.assertIsNone(part_class.get_mirror_part_id(source))

    def test_compass_pairs_unchanged(self):
        for part_class in (Part, host.part.Part):
            for source, twin in [('B_STR_A_N', 'B_STR_A_S'), ('B_STR_T_NETB', 'B_STR_T_NWTB'),
                                 ('B_STR_A_E', 'B_STR_A_W'), ('B_DECO_A_0', 'B_DECO_A_1')]:
                self.assertEqual(part_class.get_mirror_part_id(source), twin)
                self.assertEqual(part_class.get_mirror_part_id(twin), source)
            self.assertIsNone(part_class.get_mirror_part_id('CUBEROOM'))
            # same _0/_1 ending, different parts: B_GEN_1 must not become B_GEN_0
            for source in ('B_GEN_0', 'B_GEN_1', 'B_CON2_0', 'B_CON2_1',
                           'B_CON_L_0', 'B_CON_L_1', 'B_CON_R_0', 'B_CON_R_1'):
                self.assertIsNone(part_class.get_mirror_part_id(source))

    def test_legacy_host_patch_reload_and_remove(self):
        saved = host.part.Part.__dict__['get_mirror_part_id']
        def legacy(object_id):
            for left, right in Part.SUFFIX_COMPASS_ID_PAIRS:
                if object_id.endswith(left):
                    return object_id[:-len(left)] + right
                if object_id.endswith(right):
                    return object_id[:-len(right)] + left
            return Part.get_mirror_part_id(object_id)
        host.part.Part.get_mirror_part_id = staticmethod(legacy)
        self.assertEqual(host.part.Part.get_mirror_part_id('B_WNG_E'), 'B_WNG_W')
        start = len(host_patches._patched)
        try:
            for _ in range(2):
                self.assertTrue(host_patches._patch(host.part.Part, 'get_mirror_part_id',
                                                  host_patches._wrap_get_mirror_part_id, static=True))
                for source, twin in PAIRS.items():
                    self.assertEqual(host.part.Part.get_mirror_part_id(source), twin)
                for source in CATALOG:
                    if source in Part.NOT_MIRROR_PAIRS:
                        self.assertIsNone(host.part.Part.get_mirror_part_id(source))
                    elif not source.startswith('B_WNG_'):
                        self.assertEqual(host.part.Part.get_mirror_part_id(source), legacy(source))
        finally:
            while len(host_patches._patched) > start:
                owner, name, raw = host_patches._patched.pop()
                setattr(owner, name, raw)
            self.assertIs(host.part.Part.__dict__['get_mirror_part_id'].__func__, legacy)
            host.part.Part.get_mirror_part_id = saved

    def test_real_button_group_cache_and_save_roundtrip(self):
        # Enable module discovery in memory, without changing saved preferences.
        bpy.context.preferences.addons.new().module = host.__name__
        charon.materials.register()
        builder = create_host_builder_class(host.builder.Builder)()
        host.builder.set_builder(builder)
        self.assertTrue(host_patches.install())
        original = Matrix.Translation((6, -3, 9)) @ Euler((0.31, -0.48, 0.72)).to_matrix().to_4x4() @ Matrix.Scale(1.7, 4)
        center = Vector((2, 1, -4))
        # All handed wings go through the same button and cached-group path.
        try:
            for source, twin in PAIRS.items():
                part = builder.add_part(source, user_data=123, build_rigs=False)
                obj = part.object
                source_mesh = obj.data
                original_coords = coords(source_mesh).copy()
                for axis in 'XYZ':
                    obj.matrix_world = original
                    blend_utils.select(obj)
                    BuildTool.mirror(None, axis=axis, center=center)
                    self.assertEqual(obj['ObjectID'], twin)
                    twin_mesh = asset_library.load_high_res_mesh(twin)
                    self.assertIs(obj.data, twin_mesh)
                    np.testing.assert_array_equal(coords(source_mesh), original_coords)
                    # Fit + actual twin must still draw the reflected model.
                    fit = mirror_fit.fit(source, twin)
                    geometry_error = surface_error(source_mesh, twin_mesh, fit)
                    self.assertLess(geometry_error, 0.02, (source, axis, geometry_error))
                    axis_index = 'XYZ'.index(axis)
                    reflection = Matrix.Identity(4)
                    reflection[axis_index][axis_index] = -1
                    reflection[axis_index][3] = 2 * center[axis_index]
                    local_flip = Matrix.Diagonal((-1, 1, 1, 1))
                    expected = reflection @ original @ local_flip @ fit
                    self.assertLess(matrix_error(obj.matrix_world, expected), 2e-5, (source, axis))
                    # Exported ID and transform recreate the same twin placement.
                    data = part.serialise()
                    self.assertEqual(data['ObjectID'], '^' + twin)
                    restored = host.part.Part.create_matrix_from_vectors(data['Position'], data['Up'], data['At'])
                    self.assertLess(matrix_error(restored, obj.matrix_world), 2e-5)
                    cache = json.dumps({'wing': {'ObjectID': source, 'UserData': 123,
                                                Group.PROP_MATRIX_LOCAL: [list(row) for row in original]}})
                    mirrored, origin = Group.mirror_cache_data(cache, Matrix.Identity(4), axis, center)
                    child = json.loads(mirrored)['wing']
                    self.assertEqual(child['ObjectID'], twin)
                    self.assertLess(matrix_error(origin @ Matrix(child[Group.PROP_MATRIX_LOCAL]), expected), 2e-5)
                    # Two mirrors return to the original ID and placement.
                    BuildTool.mirror(None, axis=axis, center=center)
                    self.assertEqual(obj['ObjectID'], source)
                    self.assertLess(matrix_error(obj.matrix_world, original), 2e-5, (source, axis, 'double mirror'))
                print('WING_PASS', source, '->', twin, 'vertex error', round(geometry_error, 7), flush=True)
                bpy.data.objects.remove(obj, do_unlink=True)
        finally:
            host_patches.remove()
            host.builder.set_builder(None)
            charon.materials.unregister()
            bpy.context.preferences.addons.remove(bpy.context.preferences.addons[host.__name__])


suite = unittest.defaultTestLoader.loadTestsFromTestCase(WingMirrorTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise RuntimeError('Wing mirror regression failed')
