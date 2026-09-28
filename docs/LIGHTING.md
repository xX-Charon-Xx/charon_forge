# Game lighting

The **Game Lighting** controls in The Watchtower panel light a scene the way the game
does: the game's own skies, sun colours and part lamps, in EEVEE and Cycles
alike. Code:

| File | Does |
| --- | --- |
| `lighting/data.py` | the game data (`resources/lighting/`) |
| `lighting/sky.py` | the Charon Sky world node tree |
| `lighting/previews.py` | the sky pickers' swatches |
| `lighting/game_lights.py` | the part lamps as lights |
| `lighting/viewports.py` | 3D views shown the lighting, and given back |
| `lighting/rig.py` | enable / disable / apply |
| `lighting/properties.py` | `scene.charon_lighting`, place defaults, randomise |
| `lighting/presets.py` | presets on disk |
| `addon/the_watchtower_lighting_presentation.py` | the UI drawn into The Watchtower, and the Advanced sub-panel |
| `addon/the_watchtower_lighting_operators.py` | its buttons |

Settings updates always act on the scene that owns them (`self.id_data`),
never `context.scene`. The window's scene is a different scene whenever
another scene's settings change.

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
| `spacedome01.png` | `textures/space/spacedome`; R, G and B are three nebula masks |
| `nebulaplasma.png` | `textures/effects/space/nebulaplasma`; tiling nebula wisps, the filaments in alpha |
| part lamps | already in `resources/colours.json` → `objects.<id>.lights` |

**Known gap.** MBINCompiler 7.00.0.1 misreads `gcskyglobals` from the
2026-09-21 game update: every field after the first few is shifted, e.g.
DayLength reads as 1022739087. The exporter detects this and uses the decode
from the build before the update (the third argument). `globals.sky_source`
records which decode was used. The sky tables and `gcgraphicsglobals` decode
correctly.

## Using it

In The Watchtower panel, under the overlay options. It is drawn in the panel
itself, with no collapsible sub-panel.

* **Game Lighting** turns everything on and off.
* **Turning it on:** every 3D view of the scene in Solid or Wireframe switches
  to Material Preview. Scene lights and scene world are switched on, for
  Material Preview and for Rendered.
* **Turning it off:** each view gets back its scene light and world switches.
  Its shading is left alone, so a view moved to Material Preview stays there.
* **A view opened or changed since** gets a single **Show Game Lighting Here**
  button.
* **The Lamps row** appears under the button once the lighting is on. Only
  clicking **Lamps** turns the game lamps on. Turning the lighting on always
  starts them off, switching place or randomising leaves them alone, and
  presets don't store them.
* **Game Lighting: Advanced** is The Watchtower's folded sub-panel.

1. **Where:** Planet or Space. Every scene starts on Space; importing a base
   from a save sets Planet for a planet base (`HomePlanetBase`) and Space for
   every other base type. Station (Space Station, Freighter, Derelict
   Freighter, Space Anomaly) is hidden for now; its code is all still there.
   `STATION_ENABLED = True` in `lighting/properties.py` brings the button back. Picking one
   loads that place's starting values (`PLACE_DEFAULTS` in
   `lighting/properties.py`). These never touch the lamps.
2. **Sky:** on the left, the biome (planet) or star colour (space); under it
   the weather or Sky Style, with a randomise button. On the right, a small
   swatch of the sky, drawn from the game's colours; click it for the grid of
   every sky. Station has no sky colours for now: its outside is dark and
   starry, lit by the game's SpaceLightColour.
   * **Planet:** 40 generic day skies, plus the biome lists (Frozen, Swamp,
     Lava, Gas Giant), each in Clear, Firestorm or Gravity Storm weather.
     **Time** (dawn 0.25, noon 0.5, dusk 0.75, night) and **Sun** (its
     direction) share one row.
   * **Space and Station:** 58 space skies, which can be filtered by star
     colour. Space starts on rare sky 38 (`r37`, a red-star sky) as a
     Starfield. **Sky Style** decides what fills the sky:
     * **Nebula:** the game's dome with clouds and wisps.
     * **Nebula Storm:** dense, bright clouds.
     * **Galaxy:** a band of dust and crowded stars.
     * **Starfield:** stars everywhere, the nebula faded.
     * **Deep Space:** near-black with sparse stars.

     The nebula shape (set by **Random**, no slider) turns the game's dome,
     moves the clouds, wisps and galaxy band, and reseeds the stars, so every
     shape is a different sky in the same colours.
   * **Random** picks a sky, and in space also a style and shape.
3. **The look:**
   * **Brightness:** exposure.
   * **Sunlight:** the sun's strength.
   * **Glow:** every glowing surface and every game lamp at once.
   * **Lamps On/Off:** the game lamps as real lights.
4. **Advanced** (folded):
   * sky light and sky brightness;
   * sun size, disc and halo;
   * night light and noon height, or nebula, cloud and star strength;
   * view transform and look;
   * EEVEE raytracing.
5. **Presets** save every setting to
   `~/CharonForge/lighting_presets/<name>.json`.

## What the rig is

The rig itself adds nothing to any part:

* **Charon Sky** world: one node tree holding the planet sky and the space
  sky, with a Mix that picks one.
  * **Planet sky:** a gradient from fog to Horizon, Sky and SkyUpper, plus the
    sun disc (SunColour) and its halo (SkySolarColour).
  * **Space sky:** a Bottom/Mid/Top gradient, plus the nebula:
    * the game's dome (R, G, B masks → NebulaColour3, 1, 2), turned by the
      shape seed;
    * 4D-noise clouds tinted NebulaColour2;
    * the game's nebulaplasma wisps threaded through the clouds, tinted
      NebulaColour1;
    * seeded stars: bright ones, a field of faint ones, and a galaxy band
      (a tilted great circle of dust) where the faint ones crowd.

    Sky Style is a set of multipliers on these layers (`SPACE_STYLES` in
    `lighting/rig.py`). The dark styles run the nebula at 1–10%: display
    gamma lifts a linear 0.04 to a clearly visible 22% grey (measured).

    Seed 0 is the dome exactly as the game ships it.
  * **Lighting vs. camera:** Light Path > Is Camera Ray separates how strongly
    the sky lights the scene (**Ambient**) from how bright it looks
    (**Sky Brightness**).
* **Charon Sun**: one sun light in the "Charon Lighting" collection, coloured
  with the entry's LightColour.
* **Charon Game Lights** (optional): each part's game lamps become point or spot
  lights. They are not parented; a Child Of constraint makes them follow their
  part. Power = 4π × intensity × Glow, the same scale as the emission boost.
  While the lamps are on, the emission boost is off, so no lamp is counted
  twice.
* **Glow:** every glow material's strength is also multiplied by
  `1 + charon_glow_boost`, a VIEW_LAYER Attribute node that reads the scene
  property the Glow slider writes. Moving the slider touches no material.
  Materials wired before this are upgraded in place when the rig is turned on
  (`materials/emission.py`, EMISSION_VERSION 3).
* **View:** turning the rig on switches the view to Standard, because AgX
  washes the table colours to grey. Turning it off gives back the old world and
  view.

Every slider only changes node values, the sun and the exposure. No material is
touched, so dragging stays instant with any number of parts.

## Places

| Place | Sky | Light |
| --- | --- | --- |
| Planet | day sky (biome list, weather, sky) blended with dusk and night by time of day at the game's fade thresholds (0.40–0.50 sunset, 0.62–0.68 night, measured from noon) | the sky's LightColour; at night it comes from the opposite side, dimmed |
| Space | space sky (58) and nebula shape | the sky's LightColour |
| Station: Space Station, Freighter, Anomaly | dark starry sky, no colours (switched off for now) | SpaceLightColour, lower sun and sky light |
| Station: Derelict Freighter | AbandonedFreighterFogColour | dim |

## Exact and not yet exact

* **Exact:** every colour, the fade thresholds, the part lamps' position,
  colour, cone and range.
* **Guessed, to calibrate next:**
  * absolute strengths: sun W/m², ambient, sun disc, lamp power;
  * the sun's path: noon at the 55° clamp angle, heading free;
  * the sky gradient's shape and the nebula mask-to-colour mapping;
  * treating table colours as sRGB.
* **Calibration:** the base-builder icons were tried on 2026-09-28 and cannot
  calibrate lighting. Each icon has its own camera, the icons don't use default
  palettes, and shading explained about 7% of the error. What's left is Photo
  Mode screenshots with the sun locked, or the lighting shader's SPIR-V.
* **The space nebula's clouds and wisps** are how this rig adds variety, not a
  port of the game's space shader. The dome (seed 0), the colours and the star
  light are the game's.
* **Not done yet:**
  * colour-grade LUTs (`textures/lut/filters`);
  * the exact time-of-day blend (exe `0x14130f770`);
  * a sky picked from a planet or system seed (The Augur already predicts the
    indices);
  * lamps updating by themselves when parts are added (use **Refresh Lamps**);
  * station interiors built by The Forge, whose meshes carry no part id.
