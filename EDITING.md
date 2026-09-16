# Editing this site yourself

Everything lives in one folder. There is no build step for the site itself â€”
`index.html` is the whole thing.

```
portfolio-draft\
  index.html      the entire site: content, styling, and the WebGL viewer
  models.txt      which STLs become wireframes, and at what settings
  build.bat       rebuilds the wireframes after you edit models.txt
  preview.bat     starts a local server so you can see your changes
  edges\          the generated .bin files (don't edit these by hand)
  tools\          the extraction scripts
```

## Seeing your changes

Double-click **`preview.bat`**. It opens <http://localhost:8742/> and leaves a
terminal window running â€” keep that window open while you work. Edit, save,
refresh the browser. Close the window when you're done.

---

## Changing text

Open `index.html` in any editor (Notepad works; VS Code is nicer). Everything
you'd want to reword is between `<body>` and `</body>`, in plain English. Search
for the words you want to change and type over them.

Anything wrapped in `<mark>` is a placeholder â€” it shows up highlighted on the
page so you can see what still needs writing:

```html
<div class="learned"><b>What I had to work out</b><mark>[your words]</mark></div>
```

Delete the `<mark>` and `</mark>` tags along with the text inside, and write
yours in their place.

The one rule: **don't delete the angle brackets.** `<p>` opens a paragraph and
`</p>` closes it. Change what's between them freely; leave the tags alone.

## Changing colours

All colours are defined once at the very top of `index.html`, around line 15:

```css
--accent:  #d8431a;    /* the oxide orange */
--paper:   #f5f4f0;    /* page background  */
--ink:     #15171b;    /* body text        */
```

Change a hex value there and it updates everywhere. The block below it, under
`@media (prefers-color-scheme: dark)`, is the dark-mode version â€” change both or
dark mode will look wrong.

---

## Changing wireframe detail per model

This is the one that needs a rebuild. Open **`models.txt`**:

```
chess-mk1   | %USERPROFILE%\Downloads\MK1 Automatic Chess Board v24.stl | 26 | 0.005
              ^ source STL                                                 ^     ^
                                                                       angle   min length
```

**Angle** (degrees) â€” an edge is kept when the two faces meeting at it differ by
more than this.

| Value | Effect |
|-------|--------|
| 15    | lots of detail, curved surfaces start showing tessellation |
| 26    | good default |
| 38    | only the sharpest corners, very clean, can look bare |

**Min length** â€” drops edges shorter than this fraction of the model's overall
size. This is what removes fillet noise, thread detail, and tiny features that
just look like fuzz at thumbnail scale.

| Value | Effect |
|-------|--------|
| 0.000 | keep every edge |
| 0.005 | good default |
| 0.016 | aggressive â€” use for small thumbnails |

Different geometry genuinely wants different numbers. A gear needs a low angle
to keep its teeth; a printed bracket with big flat faces can take a high one.
Change the numbers, save, run **`build.bat`**, refresh.

To rebuild just one thing: `build.bat chess`

### Adding a new model

1. Add a line to `models.txt`:
   ```
   swerve-module | C:\path\to\Swerve Module.stl | 26 | 0.005
   ```
2. Run `build.bat`. It writes `edges\swerve-module.bin`.
3. In `index.html`, find the empty slot and point it at the new file:
   ```html
   <span class="mesh" data-empty></span>
   ```
   becomes
   ```html
   <span class="mesh" data-model="edges/swerve-module.bin"></span>
   ```

Optional attributes on that tag:

- `data-alpha=".95"` â€” opacity, 0 to 1
- `data-spin=".18"` â€” starting rotation in radians. Meshes sharing a value face
  the same way, which is why MK1/MK2/MK3 are directly comparable.

### Re-splitting the chess board

The MK3 flap only works because it was a separate solid in the STL. If you
change that model, redo the split:

```
python tools\shells.py "%USERPROFILE%\Downloads\Automatic ChessBoard MK3 v29.stl"
```

That lists the disconnected shells. Find the flap's number, then:

```
python tools\shells.py "%USERPROFILE%\Downloads\MK3 v29.stl" --split 0 tmp\
python tools\extract_edges.py tmp\part.stl edges\chess-flap.bin --angle 32 --minlen 0.012 --ref "%USERPROFILE%\Downloads\MK3 v29.stl"
python tools\extract_edges.py tmp\rest.stl edges\chess-body.bin --angle 32 --minlen 0.012 --ref "%USERPROFILE%\Downloads\MK3 v29.stl"
```

`--ref` is the important part â€” it normalises both halves against the *whole*
model so they still line up.

### Which way the flap opens

In `index.html`, search for `var HINGE`:

```js
var HINGE = { y: -0.104, z: -0.251, open: 0.72 };
```

- `open` â€” how far it swings, in radians. 0.72 â‰ˆ 41Â°.
- `z` â€” which edge it hinges on. Swap to `+0.174` for the opposite side.
- `y` â€” height of the hinge line.

---

## Publishing

From this folder:

```
git add .
git commit -m "what changed"
git push
```

Live about 30 seconds later.
