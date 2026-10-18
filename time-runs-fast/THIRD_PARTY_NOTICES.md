# Third-party materials

## Bundled in this skill

| File(s) | What | Author | License |
|---|---|---|---|
| `assets/fonts/CormorantGaramond_*.ttf` | Cormorant Garamond font (Light Italic, Medium, SemiBold), unmodified | Copyright 2015 the Cormorant Project Authors (github.com/CatharsisFonts/Cormorant) | SIL Open Font License 1.1 - full text in `assets/fonts/OFL.txt` |

The OFL allows bundling and redistributing the font with software, free or paid, as long as
the license text travels with it and the font is not sold on its own. The fonts are used here
unmodified, under their original names.

## Not bundled - installed separately by the user

| Tool | License |
|---|---|
| Python | PSF License |
| numpy | BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| pillow-heif (optional) | BSD-3-Clause (uses libheif, LGPL) |
| ffmpeg | LGPL 2.1+ / GPL 2+ depending on the build |
| imageio-ffmpeg (optional) | BSD-2-Clause; downloads an ffmpeg binary under its own license |

The skill only calls ffmpeg as an external program; it does not include or link it. Videos
produced with the skill are not covered by these licenses.

## Music

The tracks in `assets/music/` are written by Aion Herz (aionherz.de). Their use is governed
by `LICENSE.md`: only as the soundtrack of videos made with this skill, for private use.
