# Game lighting

The Watchtower's **Game Lighting** sub-panel lights a scene the way the game
does: the game's own skies, sun colours and part lamps, in EEVEE and Cycles
alike. Code: `src/addons/charon_forge/lighting/`, panel in
`addon/the_watchtower_presentation.py`.

## Where the data comes from

`resources/lighting/` is written by the extraction pipeline, from the unpacked
game files, by `pipeline/outputs/lighting.py`:

```bash
python -m pipeline.outputs.lighting "<unpacked game files>" "<plugin>/src/addons/charon_forge/resources/lighting" "<planet_seed_research>/mxml/gcskyglobals.globals.MXML"
```

Run it with Blender's Python, which has Pillow.

| File | From |
| --- | --- |
| `lighting.json` → `planet` | `dayskycolours`, `duskskycolours`, `nightskycolours`, `dayskycolours_firestorm`, `dayskycolours_gravstorm`. Each has a generic list plus lists for the biomes that have their own (Frozen, Swamp, Lava, GasGiant, Dark night) |
| `lighting.json` → `space` | `spaceskycolours` (10) and `spacerareskycolours` (48), with their star colour |
| `lighting.json` → `globals` | `gcskyglobals` (day/dusk/night/space light colours, sunset and night fade thresholds, derelict fog colour), `gcgraphicsglobals` (tonemap exposure, model renderer light) |
| `hdris/*.hdr` | `textures/hdris` (BC6H → HDR) |
| `spacedome01.png` | `textures/space/spacedome`; R, G and B are three nebula masks |
| part lamps | already in `resources/colours.json` → `objects.<id>.lights` |

**Known gap.** MBINCompiler 7.00.0.1 misreads `gcskyglobals` from the
2026-09-21 game update: every field after the first few is shifted, e.g.
DayLength reads as 1022739087. The exporter detects this and uses the decode
from the build before the update (the third argument). `globals.sky_source`
records which decode was used. The sky tables and `gcgraphicsglobals` decode
correctly.

## What the rig is

The rig itself adds nothing to any part:

* **Charon Sky** world: one node tree holding the planet sky, the space sky and
  the HDRI, with a Mix that picks one.
  * **Planet sky:** a gradient from fog to Horizon, Sky and SkyUpper, plus the
    sun disc (SunColour) and its halo (SkySolarColour).
  * **Space sky:** a Bottom/Mid/Top gradient, the nebula dome tinted by
    NebulaColour1–3, and procedural stars.
  * **Lighting vs. camera:** Light Path > Is Camera Ray separates how strongly
    the sky lights the scene (**Ambient**) from how bright it looks
    (**Sky Brightness**).
* **Charon Sun**: one sun light in the "Charon Lighting" collection, coloured
  with the entry's LightColour.
* **Charon Game Lights** (optional): each part's game lamps become point or spot
  lights. They are not parented; a Child Of constraint makes them follow their
  part. Power = 4π × intensity, the same scale as the emission boost. While the
  lamps are on, the emission boost is off, so no lamp is counted twice.
* **View:** turning the rig on switches the view to Standard, because AgX
  washes the table colours to grey. Turning it off gives back the old world and
  view.

Every slider only changes node values, the sun and the exposure. No material is
touched, so dragging stays instant with any number of parts.

## Contexts

| Context | Sky | Light |
| --- | --- | --- |
| Planet | day entry (biome list, weather, index) blended with dusk and night by time of day at the game's fade thresholds (0.40–0.50 sunset, 0.62–0.68 night, measured from noon) | entry LightColour; at night it comes from the opposite side, dimmed |
| Space | space entry (common / rare, index) | entry LightColour |
| Station, Freighter, Anomaly | space entry | lower sun and ambient; game lamps on |
| Derelict Freighter | AbandonedFreighterFogColour | dim; game lamps on |
| Catalogue | a game HDRI | no sun |

Choosing a context loads its starting values (`CONTEXT_DEFAULTS` in
`lighting/properties.py`). **My Presets** saves every setting to
`~/CharonForge/lighting_presets/<name>.json`.

## Exact and not yet exact

* **Exact:** every colour, the fade thresholds, the part lamps' position,
  colour, cone and range.
* **Guessed, to calibrate next:**
  * absolute strengths: sun W/m², ambient, sun disc, lamp power;
  * the sun's path: noon at the 55° clamp angle, heading free;
  * the sky gradient's shape and the nebula mask-to-colour mapping;
  * treating table colours as sRGB.
* **Calibration plan:** fit the strengths against the game's base-builder icons
  (Catalogue context) and against Photo Mode screenshots taken with the sun
  locked.
* **Not done yet:**
  * colour-grade LUTs (`textures/lut/filters`);
  * the exact time-of-day blend (exe `0x14130f770`);
  * a sky picked from a planet or system seed (The Augur already predicts the
    indices);
  * lamps updating by themselves when parts are added (use **Refresh Lamps**);
  * station interiors built by The Forge, whose meshes carry no part id.
