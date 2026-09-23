# Materials, colours, finishes and glow

How Charon Forge colours the high-res parts, and why each part works the way
it does. Everything here follows the game's own data. None of it is tuned by
hand.

Code: `src/addons/charon_forge/materials/`, and the Colours panel in
`src/addons/charon_forge/addon/colours*.py`.

---

## 1. Where the data comes from

The high-res library (`asset_browser/assets/*.blend`, `textures/`, `icons/`)
and `resources/colours.json` are written together by the extraction pipeline
(`nms assets extraction pipeline`). It reads them straight from the game files:

| Game file | What it gives |
| --- | --- |
| `BASEBUILDINGOBJECTSTABLE` | each part's palette group, station palette group, finish group, default palette, default finish, and whether it can change finish |
| palette and material tables | every palette's four colours, every finish, and the finish groups |
| each part's `.MATERIAL.MBIN` files | material class, flags, textures and colour, stamped onto every material |
| `TEXTURES/MULTITEXTURES/*` arrays | the finish textures: one texture slice per finish |
| each part's scene `LIGHT` nodes | position, colour and intensity of the part's lamps |

`materials/game_data.py` is the only code that reads `colours.json`. It
reloads the file if it changes on disk.

When a new game update is extracted, copy the new `library/assets`, `textures`,
`icons` and `library/addon/colours.json` into the plugin. Nothing else needs
to change.

---

## 2. The one rule: colour lives on the object

A part's materials and mesh are **shared by every placement of that part**.
One mesh and one set of materials serve a thousand copies. So nothing that
differs between placements may live on a material. The shaders read it from
the **object** instead, through Attribute nodes of type `OBJECT`:

| Object property | Read by | Meaning |
| --- | --- | --- |
| `nms_p`, `nms_s`, `nms_t`, `nms_q` | the `NMS_Colourise` node group | the palette's primary, secondary, ternary and quaternary colours (RGBA) |
| `nms_finish` | the finish switch in each finish-capable material | which finish texture slice to show |
| `UserData` | Charon Forge, and saves | the packed palette and finish, exactly as the game stores it |
| `readonly:Colour`, `readonly:Material` | the viewport overlay | readable palette and finish names |
| `object.color` | Solid shading set to *Object* colour | the palette's primary colour |

So recolouring a part means five property writes. No material is copied and
nothing is duplicated. **Never copy a mesh or material to recolour a part.**

### UserData

```
palette index = UserData & 0xFFFFFF        (bits 8, 16 and 17 are not colour - never touched)
finish index  = (UserData >> 24) & 0xFF
encode        = (finish << 24) | palette
```

The finish index is **the finish's own index**, not its position in a group.
The `RUSTED` group holds only `MAT_RUSTED`, and that finish is still 1. It is
also the texture slice the finish shows, so `nms_finish = UserData >> 24`,
unchanged.

---

## 3. Palettes

`colours.json → palettes` lists every palette (151 in the Cosmos build) by the
index `UserData` stores, each with four RGBA colours. Palette groups say
which palettes a part may use:

| Group | Used by (count of parts) |
| --- | --- |
| `LEGACY` (16) | classic base parts (~610) |
| `BIGGS` (16) | corvette parts (~640) |
| `STATIONBASE` (36) | space-station parts; also the *second* group of 37 freighter parts |
| `FREIGHTERBASE` (16) | freighter parts |
| `COLOURS_B` / `_F` / `_T` / `_S` (8–11 each) | Salvaged, Fiberglass, Timber and Stone structure sets |
| `FLAGS` | flags |
| *(none)* | 454 parts the game does not let you recolour |

Rules Charon Forge applies:

* **A new part gets the game's default**: its own default palette and
  finish, taken from the objects table. Corvette parts start on BIGGS0 with
  Gloss, station parts on STATION0, timber on Oak with Polished Timber. The
  plugin used to start every part on palette 0.
* **Any palette can go on any part.** The game's build menu only offers a part
  its own group(s). Charon Forge offers every palette to every part and
  applies exactly what UserData says. The part's own groups are listed first
  in the panel and marked *(this part)*.

### How a palette reaches the pixels

Every colourable material (game flag `_F53_COLOURISABLE`) has a
`NMS_Colourise` group, fed by the diffuse and the part's own colourise mask.
The mask is a selector on a quarter grid. The group rounds it to the nearest
slot: above 0.875 primary, above 0.625 secondary, above 0.375 ternary, above
0.125 quaternary, below that unpainted. The chosen colour multiplies the
diffuse. Station decor tiles (`DecorTile1_MAT`) have no mask in the game. The
pipeline builds one from the layers of their procedural texture.

Some colourable materials have no mask at all (`CaveLeaves_Mat` on
`BASE_CAVE2`, the lava on `BASE_CAVE5`) and so get no `NMS_Colourise` group
from the pipeline. `materials/colourise.py` multiplies their diffuse by
`nms_p` when they are loaded, so the whole surface takes the primary colour.

---

## 4. Finishes

A finish is a **different set of textures**, not a tint. The game stores a
part's diffuse, masks, normal and colourise mask as texture arrays, one slice
per finish. The pipeline exports every slice (`BIGGSTRIM.F2.png` ...) and puts
all of a material's slices into it, behind a switch that reads `nms_finish`. A
finish index past the last slice shows the last slice, which is what the GPU
does with an out-of-range array layer.

| Finish group | Finishes (index) | Texture set |
| --- | --- | --- |
| `ALL` | 0 Concrete, 1 Rust, 2 Stone, 3 Wood | BASEBUILDINGEXTERIOR and the trims |
| `BIGGS` | 0 Gloss, 1 Inverted Gloss, 2 Weathered, 3 Metallic | BIGGSTRIM |
| `T_ALL` | 0 Polished Timber, 1 Weathered Timber | WOODTRIM |
| `S_ALL` | 0 Polished Stone, 1 Aged Stone | STONETRIM |
| `F_ALL` | 0 Polished Alloy, 1 Rusted Alloy | FIBERGLASSTRIM |
| `B_ALL` | 0 Polished Salvage, 1 Rusted Salvage | BUILDERSTRIM |

What the slices change, measured per slice by the pipeline
(`library/addon/COLOURS.md` has the full table):

* **Inverted Gloss** changes only the colourise mask, which swaps the primary
  and secondary regions. Charon Forge must not swap the colours itself, or the
  swap happens twice.
* **Metallic** changes only the masks, which raises metalness.
* **Weathered, Rust, Stone, Wood, Aged, Rusted** change diffuse, masks and
  normal.

Setting a finish is only `nms_finish` (plus `UserData`). The finish icons in
the panel are the game's own (`asset_browser/icons/finishes/`).

> **Replaced:** earlier versions faked finishes with hand-tuned
> roughness/metal/tint offsets from `resources/finishes.json`, spliced in
> front of every Principled BSDF. That file is gone. Opening an older scene
> removes those nodes (`finish_nodes.strip_legacy_finish_nodes`) and restores
> whatever fed each socket before. The old
> `nms_finish_rough/metal/polish/tint/tint_mix` object properties do nothing
> any more; each part drops them the next time it is coloured.

---

## 5. Glow

The game decides per material whether a surface glows, from its material
class and flags. The pipeline stamps both onto every material (`nms_class`,
`nms_flags`), and `materials/emission.py` wires emission from them once per
material:

| Game material | Game behaviour | In Blender |
| --- | --- | --- |
| flag `_F07_UNLIT` (~2270 materials) | drawn with no lighting | emits its diffuse, base colour black (done by the pipeline) |
| class `Glow`, `GlowTranslucent`, `Bloom` with a masks texture | glows **only where masks blue is set** | emission = surface colour × masks.B |
| the same classes without a masks texture | glows all over | emission = surface colour |
| class `Additive`, `GunAdditive`, `DoublesidedAdditive` | light added onto the scene | emission = surface colour |

Measured facts behind the masks rule:

* The blue channel is **0 on every ordinary texture** (BIGGSTRIM,
  BASEBUILDINGEXTERIOR, ROVERTRIM).
* On glow-class trims it covers about 1% of STONETRIM and WOODTRIM.
* Those texels are the light strips: mean diffuse 0.91–0.97 there, against
  0.44–0.54 overall.
* "Glow" is the class of ordinary stone and timber trim too, so making the
  whole surface glow would light up entire walls.

Before this pass, 555 glow-class materials had no emission at all, including
the corvette exterior lamps, glow plants and the trim light strips.

### Lamps that light the scene

A placed part is **one object with no children**. No Blender light objects are
added, so the glowing surfaces themselves are the lamp. Emission lights its
surroundings in Cycles, and in EEVEE with raytracing on. At strength 1,
though, a lamp's few square centimetres of glow throw almost nothing.

So every glow material's strength is multiplied by `max(1, nms_glow)`. Blender
looks that property up on the object, then on its mesh. When a part's mesh
loads, it gets:

```
nms_glow = (4π × Σ intensity of the part's game LIGHT nodes) / (area of its glowing faces)
```

The game's lights fall off as `intensity / d²`. A Blender emitter of P watts
gives `P / (4π d²)`, so the game light's power is `4π × intensity`. That power
is spread over the surfaces that glow. Some examples:

| Part | Game light power | nms_glow |
| --- | --- | --- |
| WALLLIGHTRED | 28 W | 132 |
| CEILINGLIGHT | 79 W | 54 |
| LIGHT_TALL | 308 W | 364 |

Details:

* A part with no game lights has no `nms_glow`. It reads 0, and its glow stays
  at strength 1.
* Lights inside effect scenes (beams, sparks) are left out.
* The boost is capped at 2000.
* The panel's **Lamps Light the Scene** toggle switches every lamp between its
  game power and plain glow (strength 1). The game value is kept on the mesh
  as `nms_glow_lamp`.

---

## 6. The Colours panel

*3D Viewport → sidebar → Charon Forge → Colours*. It shows the **active**
part's options and applies to **every selected** part:

* **Header**: the part id, and its current palette and finish.
* **Finish**: the part's own finish set with the game's icons. The current
  finish is shown pressed. A finish is a slice of the part's own textures,
  so only its own set is shown. Parts with no finish textures have no row.
* **Palettes**: every palette the game defines, 151 in the Cosmos build.
  They are grouped as the game groups them: the active part's own group(s)
  first, marked *(this part)*, then every other group, then *Other palettes*
  that belong to no group (NEUTRAL, BUILDERSB*, FIBREGLASSB*/C*). The current
  palette is shown pressed. Hovering a swatch gives its name and id.
* **Swatches** look like the base builder add-on's
  (`images/colours/*.jpg`) and sit in the same grid: 12 columns at 0.6
  width. Each is 150 × 100, with a 4 px border in the primary colour at 60%,
  the primary colour on the left and a stripe on the right. The stripe is the
  secondary colour, or the ternary for FREIGHTERBASE palettes, as that add-on
  draws them. All 90 of its swatches that match a game palette are
  reproduced within 2.7/255. Ours are generated from `colours.json`, so all
  151 palettes have one and a game update needs no new images. They are
  cached as PNGs in Blender's user data folder
  (`datafiles/charon_forge/swatches`), named by their colours.
* **Game Default**: the part's default palette and finish.
* **Copy From Active**: the active part's palette and finish onto the other
  selected parts, each still limited to what the game offers it.
* **Lamps Light the Scene**: see above.

Fbx proxy parts have no textures to switch, so they still get the flat
material for the chosen palette index. The base builder add-on's own colour
panel keeps working too: its calls reach high-res parts through
`HighResMaterialsMixin` and go through the same game rules.

---

## 7. When materials are prepared

| Moment | What runs |
| --- | --- |
| a part's asset is appended (`asset_library.load_high_res_mesh`) | mesh tagged `nms_high_res_id`, duplicate faces removed, `nms_glow` computed |
| a part is placed (`placement.add_part`) | UserData = game default unless given; colour applied; that mesh's materials prepared |
| a save is imported (`importer.import_objects`) | all parts coloured in one pass; textures and node groups deduplicated; all materials prepared |
| a `.blend` is opened | all materials prepared; lamp boost added to library meshes that lack it |

"Prepared" means the old finish nodes are stripped and glow is wired. Each
material is tagged (`charon_emission`), so each step is done only once.

---

## 8. Reference: properties on materials (written by the pipeline)

| Material property | Meaning |
| --- | --- |
| `nms_material_path` | the exact `.MATERIAL.MBIN` it was built from |
| `nms_class` | the game's MaterialClass |
| `nms_flags` | the game's material flags |
| `nms_finish_rig` | has the `nms_finish` slice switch |
| `nms_texture_variants` | alternate procedural textures (rust, stealth, ...), switched by object properties `nms_tex_*` |
| `nms_diffuse_gain` | the gain the pipeline applied to the diffuse |
| `charon_emission` | set by Charon Forge once glow is wired |

## 9. Troubleshooting

| Symptom | Cause |
| --- | --- |
| a part renders black where it should be coloured | its object lost `nms_p/s/t/q`. Apply a palette or **Game Default** |
| finish buttons missing | the part has no finish textures (no finish group in the game) |
| lamps glow but light nothing | **Lamps Light the Scene** is off, or EEVEE is used without raytracing |
| colours look wrong after a game update | `colours.json` and the library come from different pipeline runs. Always copy them together |
