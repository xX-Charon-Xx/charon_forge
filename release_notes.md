release 0.1.0
-------------

The first release of **Charon Forge**: build No Man's Sky bases and corvettes in Blender with the game's real, high-resolution models, then put them straight back into your save.

**Requires Blender 4.5 or newer.** To install, drag the `charon_forge-*.zip` onto the Blender window and click **Install**. Or use **Edit > Preferences > Get Extensions**, the dropdown, then **Install from Disk...**

### Building with the game's real parts

* Every part is the game's own high-resolution model, textured and coloured as it looks in game.
* In-game palettes and finishes, on single parts and on groups. Groups keep their colour, and colouring a group colours every part in it.
* Switch the whole scene between **High-res** and lighter **Simple Proxies**. **Fix Scene** reloads every part and texture.
* Fossils are built from the high-resolution models too.
* Mirrored parts come out facing the right way, in Blender and in game.

### Asset Browser

* Every buildable part in its own window, by category, with thumbnails.
* Search, **Favourites**, **Recent Items** and **Presets**. Pin and reorder categories.
* Each part's options list all its **variants**, the main one first, plus **Replace Selected Objects**.
* A **Charon** menu in the viewport header, with quick access to favourites and recents, and a search showing the best eight matches.

### Optimiser

* Saves the parts that matter most first, following an editable **Priority List** of part groups.
  * Rename, reorder, add and delete groups.
  * Preview each group's parts as thumbnails.
* **Auto Optimise** reorders on every save and export. **Optimise Now** reorders right away.
* **Primary cockpit and landing bay**, picked automatically on import and when the first one is placed.

### Crossing: import and export

* Import and export `.nmsship` corvettes, and `.json` / `.txt` part lists.
* Import and export through the clipboard: just the parts, or the whole base.
* Importing replaces the previous build. `Ctrl+Z` brings it back.

### The Watchtower

* An overlay in the viewport:
  * the base's name, its type (planet base, corvette, freighter, space base, space station base...) and its part count;
  * the selected part's id, name, colour and material.
* Floating **Cockpit** and **Landing Bay** labels over the primary parts.

### The Forge

* **Forge a Shape:** spheres, cuboids, other solids, circles, squares and polygons, made from copies of any part.
  * They stay adjustable, update live, and split back into parts when you're done.
* **Forge a Symbol:** turn any text or link into a scannable **QR code**, built from as few storage panels as possible.
* **Forge Space Station:** build a full space station from the game's own models to design a base inside it.
  * Design your own, or enter a **Galactic Address** for that system's station.

### Helmsman

* Review a batch of ships:
  * import any of them to look at it;
  * add notes, approve or reject each one, and give it a corvette slot.
* Write every assigned ship into your save in one go, with a backup made first. Then export the results.

### Works alone, or with the Base Builder addon

* Charon Forge works on its own.
* With the **No Man's Sky Base Builder** addon installed, its tools place and colour Charon's high-resolution parts. The release version of that addon is found automatically.
* Features that need that addon say so when it isn't installed.
