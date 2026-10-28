# B_WNG mirror audit (22 October 2026)

The mirror ID lookup checked generic compass suffixes before the wing family.
In B_WNG IDs, the final letter or number identifies a model, not a compass
heading or handedness. The same ordering is present in the inspected
[upstream Base Builder source](https://github.com/djmonkeyuk/nms-base-builder/blob/master/src/addons/no_mans_sky_base_builder/part.py).

## Confirmed collisions

| Source | Previous result | Correct mirror | Effect before this fix |
| --- | --- | --- | --- |
| B_WNG_E | B_WNG_W | B_WNG_E_R | Missing twin; Osprey wing did not swap models or receive its measured twin fit. |
| B_WNG_N | B_WNG_S | B_WNG_N_R | Missing twin; Arcadia heavy booster did not swap models or receive its measured twin fit. |
| B_WNG_O_0 | B_WNG_O_1 | B_WNG_O_0_R | Rockhopper wing silently became a propeller. |
| B_WNG_O_1 | B_WNG_O_0 | B_WNG_O_1_R | Rockhopper propeller silently became a wing. |

Their _R counterparts returned the base ID correctly, but the reverse lookup
was wrong; mirroring twice therefore failed to restore the original part.
The numbered collisions are especially easy to miss because both incorrect
IDs exist in the catalog. Testing only for existence or reciprocal lookups
would not detect a wing/propeller swap.

## Other wing exceptions

- B_WNG_R is the base Aeron blade. Its handed twin is B_WNG_R_R. Removing the
  final _R from the base would yield the nonexistent B_WNG. Preserve this pair.
- B_WNG_P_T, B_WNG_P_B, B_WNG_R_T and B_WNG_R_B have no separate handed twins in
  either supplied catalog/model library. The lookup now returns None instead
  of inventing *_T_R or *_B_R IDs. They retain the tool's existing transform-only
  behavior; this change does not add assets or promise an exact geometric
  reflection for those four variants.
- B_WNG_O_2 correctly pairs with B_WNG_O_2_R; its suffix did not collide.
- The remaining A-D, F-M, P and Q handed pairs follow the regular _R rule.

## Changes

Both supplied plugin source trees now resolve the wing family before generic
compass suffixes. Non-wing compass behavior is preserved.

Charon's host_patches.py also wraps the installed Base Builder Part class's
get_mirror_part_id method. This makes the corrected wing rule available when
Charon is used with an older Base Builder release, and keeps single-part
buttons, builder swaps, group caches and mesh-fit corrections consistent.
The wrapper delegates all non-wing IDs to the host and is restored on removal.

No asset geometry or mirror-fit algorithm needed changing for the 40 handed
wing variants. No installed Blender extension folders or existing release ZIPs
were modified. A new installable Charon package is provided at
`dist/wing-mirror-fix/charon_forge-0.1.2.zip`. Install that ZIP through Blender's
Extensions menu (Install from Disk), then restart Blender. It retains version
0.1.2; select the reinstall/replace option if Blender reports that version is
already installed. Updating Charon alone supplies the compatibility fix while
Charon is enabled. The Base Builder source fix is also present for future builds.

## Verification

Passed with Blender 5.2.2 LTS in a factory-startup background process:

- All 44 catalog wing IDs: 20 handed pairs (40 IDs), four without handed twins.
- Correct counterparts exist in both catalogs and Charon's asset library.
- Real BuildTool.mirror calls for each of the 40 handed IDs on X, Y and Z,
  with a rotated, translated, uniformly scaled object and an offset mirror center.
- Each button operation displays the twin's own mesh without modifying the
  cached source mesh. Measured twin alignment agrees with the reflected source;
  the largest sampled bidirectional mean vertex distance was about 0.003434
  model units. This checks geometry, not a rendered screenshot.
- Mirroring twice restores the ID and original transform.
- Serialized ObjectID and Position/Up/At recreate the displayed transform.
- Group.mirror_cache_data produces the same twin ID and world transform.
- An emulated old host with the original compass-first bug is corrected by
  Charon's wrapper; repeated wrapping/removal restores the original static method.
- The wrapper preserves results for every non-wing entry in Charon's catalog.
- git diff --check passes in both source trees for the changed files.

This was Blender-side verification, including save-transform reconstruction;
no live game import was performed. Auto-duplicate and change-orientation modes
were outside this regression's scope.

Reproduce from the Charon Plugin repository (adjust the host path as needed):

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' `
  --background --factory-startup --python-exit-code 1 `
  --python tests/wing_mirror_regression.py -- `
  --host-addon '../Official/nms-base-builder/src/addons/no_mans_sky_base_builder'
```


## Follow-up: installed Rockhopper fix

A subsequent check found that the installed Official add-ons in Blender 5.1
and 5.2 still used the old compass-first lookup. The installed Charon in 5.1
already contained the fixed lookup and compatibility wrapper, and returned the
correct counterpart after a fresh startup. The earlier source/package fix had
not replaced the standalone Official installations.

The installed Official `part.py` lookup was patched directly in both versions,
with the original bytes retained alongside each file as
`part.py.before-wing-mirror-fix.bak`. The older Blender 4.5 development copy was
left alone; it did not reproduce the Rockhopper type-changing bug.

Real installed-button checks passed for all six Rockhopper IDs (_0, _1, _2
and their _R twins), on X/Y/Z, including double mirroring and serialized IDs:

- Blender 5.1.2 with Charon + Official enabled.
- Blender 5.1.2 with Charon disabled in memory and Official alone.
- Blender 5.2.2 LTS with Official alone.

The full 44-ID, geometry, group-cache and save-transform regression also passed
against the installed 5.1 add-on files. These checks used separate background
Blender processes without saving scenes or preferences. Restart Blender to
load the patched files. Existing objects already changed into a different
model retain their current ID; undo the earlier operation or recreate the
intended part before mirroring it again.

`tests/installed_rockhopper_mirror.py` exercises the enabled installed add-ons
using normal Blender preferences. `tests/wing_mirror_regression.py` also accepts
`--charon-addon` to verify an installed Charon directory.
