"""Run in background Blender with normal preferences to exercise installed buttons.
No scenes or preferences are saved. Charon is disabled in memory for the final pass.
"""
import importlib
import sys
sys.dont_write_bytecode = True
import addon_utils
import bpy
from mathutils import Vector

host_name = next(name for name in bpy.context.preferences.addons.keys()
                 if name.endswith('.no_mans_sky_base_builder') and name in sys.modules)
host = sys.modules[host_name]
builder_module = importlib.import_module(host_name + '.builder')
BuildTool = importlib.import_module(host_name + '.tools.build_tool').BuildTool
blend_utils = importlib.import_module(host_name + '.utils.blend_utils')
rockhopper = ['B_WNG_O_0', 'B_WNG_O_1', 'B_WNG_O_2']
pairs = {root: root + '_R' for root in rockhopper}
pairs.update({right: left for left, right in list(pairs.items())})

def check(mode):
    builder = builder_module.get_builder()
    for source, twin in pairs.items():
        part = builder.add_part(source, user_data=0, build_rigs=False)
        obj = part.object
        blend_utils.select(obj)
        for axis in 'XYZ':
            BuildTool.mirror(None, axis=axis, center=Vector((0, 0, 0)))
            assert obj['ObjectID'] == twin, (mode, axis, source, obj['ObjectID'])
            assert part.serialise()['ObjectID'] == '^' + twin
            BuildTool.mirror(None, axis=axis, center=Vector((0, 0, 0)))
            assert obj['ObjectID'] == source, (mode, axis, 'double', obj['ObjectID'])
        print('INSTALLED_BUTTON_PASS', bpy.app.version_string, mode, source, twin, flush=True)
        bpy.data.objects.remove(obj, do_unlink=True)

charon_names = [name for name in bpy.context.preferences.addons.keys()
                if name.endswith('.charon_forge') and name in sys.modules]
if charon_names:
    check('Charon + Official')
    for name in charon_names:
        addon_utils.disable(name, default_set=False)
check('Official alone')
print('INSTALLED_ROCKHOPPER_OK', bpy.app.version_string, flush=True)
