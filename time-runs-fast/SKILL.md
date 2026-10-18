---
name: time-runs-fast
description: Turns family photos and home videos into an emotional, cinematic music film where the viewer watches a child - or two or three siblings - grow up - media sorted by the children's age from newborn to today, the best moments with them cut from the videos, the user's own song chosen by language (English, German or Russian). Use whenever the user wants a slideshow, photo film, memory video, birthday or anniversary video, or "a video from these photos/videos" - also in Russian or German (видео из фото, слайдшоу, фильм из семейных фото, как рос ребёнок, как росли дети, Diashow, Fotovideo, Video aus Fotos, wie mein Kind aufgewachsen ist), even if the skill is not named.
---

# Time Runs Fast

The user gives family photos and home videos (attached in chat or a folder on their computer).
You produce one MP4: their song plays and their child (or children) grow up on screen - photos
with slow camera moves and soft transitions, plus short living moments cut from the videos.
The children are the main characters. Do not ask whose film it is:

- **Default - all the children in the material**: one family timeline in real time, sorted by
  the children's growing ages. The first-born's early years come first, then each younger
  child's birth appears at its true place in the story (e.g. the older one holding the newborn).
  Keep the siblings balanced - each gets a fair share of screen time - and favor shots of
  them together: they are the strongest.
- **One child only** - when the user names a child or says "my son" / "my daughter" and the
  material has several: that child's story; keep pictures where that child is clearly present.

The emotional effect comes from three things you control: the **order** (a believable
timeline of the children growing), the **choice** (faces, eye contact, laughter, hugs,
milestones - not filler), and the **pace** (each image gets enough time to be felt). The
script handles the look (motion, transitions, warm grade, vignette, fades, music).

`SKILL_DIR` below means the folder containing this file. Run the scripts by their full path.
Use `python3` on macOS/Linux and `python` (or `py`) on Windows. Talk to the user in their language.

## 1. Ask first: the video format

Right at the start, before anything else, ask which format to make - as a numbered list the
user answers with one number:

```
Which video format should I create? Reply with a number:
1. 9:16 vertical (phone, Reels, TikTok, Shorts)
2. 16:9 horizontal (TV, YouTube)
3. 1:1 square
4. 4:5 (Instagram feed)
```

Write it in the user's language and map the number to `--format` (1 -> `9:16`, 2 -> `16:9`,
3 -> `1:1`, 4 -> `4:5`). Ask in the same message for the language if it is not clear: English /
Deutsch / Русский (picks the song `assets/music/<en|de|ru>.*`). Skip a question only when the
request already answers it. If nobody can answer, use the conversation's language and 9:16.

## 2. Check the environment (once per session)

```
python3 SKILL_DIR/scripts/make_video.py --check
```

- `ffmpeg: MISSING` -> give the install line for their OS: macOS `brew install ffmpeg`,
  Windows `winget install Gyan.FFmpeg` (then a new terminal), Linux `sudo apt install ffmpeg`,
  or `python3 -m pip install imageio-ffmpeg` on any OS.
- Missing numpy/Pillow -> `python3 -m pip install numpy pillow`. iPhone HEIC photos -> `pillow-heif`.
- The check also shows which songs exist in `assets/music/`.

## 3. Collect the media

- **Files attached in chat**: find them on disk (in Claude.ai under `/mnt/user-data/uploads/`).
  If attachments exist only in the conversation and not as files, ask for the folder path.
- **A folder path**: use it; add `--recursive` when the archive has subfolders.

## 4. Look at everything

```
python3 SKILL_DIR/scripts/scan_media.py <files or folders> --out-dir <work>/sheets [--recursive]
```

It prints a table (P1, P2... with EXIF date and camera; V1, V2... with creation time and length)
and writes overview images with a light coordinate grid (every 0.1, labelled every 0.2,
0,0 = top-left). **Open every sheet image and look at it.** First identify the children who
recur across the material and tell them apart (give each a working label like "older girl",
"younger boy"), so you can follow each of them from picture to picture. Then, for every photo
and every video moment, note:

- **the important area - always, first.** The children are the subject of the film. Draw a box
  around the child or children of interest *with what makes the moment*: the whole child on
  the balance bike including the bike, the child and the birthday cake, the two siblings
  hugging, the baby in the father's arms. If several children are in the picture, the box
  holds all the children who matter there. It is not just a face. Read the corners off the
  grid as `area=X0,Y0,X1,Y1` (left, top, right, bottom). For a video moment, the box covers
  where the children are during those seconds (look at the frames of that moment).
- each child's approximate age, who else is there, the situation, quality, emotion.

## 5. Order: the children grow up

Sort by when each picture was taken, youngest first.

- The children's faces are the clock. Estimate each child's age (newborn, ~3 months, ~6 months,
  1 year, toddler, preschool, school age, teen...). Babies change fastest, so in the first two
  years order carefully month by month (size, hair, teeth, sitting/crawling/walking).
- With siblings, the age gaps never change: once you know them (e.g. the boy is ~3 years
  older), any child in a picture dates it, and a picture of the older one alone still has a
  clear place relative to pictures of the younger one. Check consistency: in the final order
  every child should only get older.
- Pictures where none of the children is clearly visible: leave them out unless they clearly
  belong to the story (e.g. the pregnancy, the parents waiting at the hospital).
- EXIF date / video `creation_time` is strong evidence when a camera model is present and the
  date is plausible. Distrust it for scans, messenger copies and edits: dates like 1970 or
  2000-01-01, or dozens of files sharing one date (that is the import date). If the date and
  the faces disagree, trust the faces.
- Keep one event together (all birthday shots in a row), calm shots before lively ones.
- Open with the earliest, tenderest picture (the first-born as a newborn). Close with the most
  recent, ideally all the children together looking into the camera, or a warm family shot.
- Drop near-duplicates (keep the best of a burst), blurry or dark shots, screenshots,
  documents, memes, pictures without people unless they clearly matter.

## 6. Pick the moments from each video

On the video sheet, find moments with the children: faces visible, siblings playing together, laughing,
hugging, first steps, blowing out candles, dancing, running towards the camera, splashing.
Avoid shaky pans, backs of heads, empty rooms, darkness, someone filming a screen.

- Zoom into a promising range to choose the exact start:
  `scan_media.py <video> --out-dir <work>/sheets --from 40 --to 55 --step 0.5`
- A moment is **5 s** (`dur=5`) - longer than a photo, which stays about 4 s. Use less only when
  the video ends sooner or the good part is shorter. Start just as the action begins. Usually
  1-3 moments per video; a long video with many great moments can give more.
- Place each moment in the timeline by the children's ages, like a photo.
- The original sound is muted - the song plays throughout - so choose moments that work silently.

## 7. Fit the song

The photos and videos run exactly as long as the song: the series ends when the music ends, and
the song has faded out by then. After that the film goes on for 10 s on a white closing card, so
it is song length + 10 s. The script gives each video moment its own length (5 s) and shares the
rest between the photos (about 4 s each is ideal; the first and last linger longer).

- Keep video moments to roughly a third of the song so the photos can breathe.
- Too much material (a photo would get under ~2.5 s, the script warns below 1.8 s): pick a subset -
  best faces and emotions, every age of every child represented evenly, varied shots (close-ups, whole family,
  outdoors). Tell the user how many you left out.
- Too little material: fine - the script repeats the photos in a second cycle with different
  camera moves and a gentle dip to black between cycles.

Song length: the render prints it. To know it before choosing, run
`ffmpeg -i SKILL_DIR/assets/music/<lang>.mp3` and read `Duration`.

## 8. Write the order file

One item per line, in display order, absolute paths, `#` for comments. **Every** photo and
video moment gets its important area; video moments also get `start` and `dur`:

```
# newborn
/Users/anna/Family/2015/IMG_0012.jpg [area=0.30,0.25,0.75,0.80]
/Users/anna/Family/2015/IMG_0031.jpg [area=0.10,0.20,0.90,0.95]
# first steps
/Users/anna/Family/2016/VID_0040.mp4 [start=12.5 dur=5 area=0.20,0.30,0.65,1.00]
# balance bike - the whole child with the bike
/Users/anna/Family/2018/IMG_1180.jpg [area=0.38,0.30,0.70,0.92]
```

**How the camera uses the area.** Every camera move starts or ends on a framing that shows the
whole area with a margin around it, centred - a zoom-in travels from the whole picture to the
children and stops there; a zoom-out starts on them; slow pans and rises settle on them. The
camera never goes closer than that framing, so a child is never cut off, and never closer than
1.3x (1.6x for photos shown whole and smaller), so the moment keeps its surroundings. A bigger
area means a gentler zoom - include the bike, the cake or the hug when they are part of it.

**fill.** A photo whose shape differs a lot from the film format (a landscape photo in a 9:16
film, a portrait photo in 16:9) is shown whole, smaller, over a blurred copy of itself. That is
right for group shots. For a close-up of one child whose area is narrow enough, add `fill`
(`[area=... fill]`): the photo then fills the whole frame, cropped around the area. Use it only
when the area and nothing else important fit in the crop (a vertical crop keeps about the middle
40% of a landscape photo's width).

## 9. Render

```
python3 SKILL_DIR/scripts/make_video.py --order-file <work>/order.txt --lang ru --format 9:16 \
    --engine Claude --out <output folder>/time-runs-fast_ru_9x16.mp4
```

- **Closing card**: when the music ends, the last picture has melted into a warm white card
  that stays for 10 more seconds, in silence. It says, in the chosen language, which AI the
  film was made with, that it used the free skill
  *Time runs fast*, the music credit "Time runs fast - Aion Herz" and the page aionherz.de.
  Always pass `--lang` (it sets the card's language as well as the song) and `--engine` with
  the name of the AI you are running as: `Claude` (Claude.ai, Claude app, Claude Code) or
  `Codex`. Keep the card - it is part of the skill; drop it with `--no-end-card` only if the
  user explicitly asks.

- `--preview` renders at half resolution, several times faster - offer it when the user wants
  to check the order first or the song is long.
- `--look warm` (default), `film` (nostalgic, softer colors, light grain - nice for archives full
  of old scans), `natural` (no grading).
- `--seed N` makes the camera moves and transitions reproducible; change it for a different variant.
- Rendering takes roughly 1-3x the song length on a laptop and uses all CPU cores. Run it in the
  background if your environment allows and keep the user informed.
- Output folder: in Claude.ai `/mnt/user-data/outputs/`; otherwise next to the user's media
  (or where they asked).

## 10. Check, then deliver

Pull 3-4 stills from the result and look at them - nothing black or broken, faces not cut off:
`ffmpeg -ss 10 -i film.mp4 -frames:v 1 check_10s.jpg`.

Then tell the user briefly: where the file is, its length, how many photos and video moments
went in, the timeline in one line (e.g. "newborn -> first steps -> kindergarten -> school"), and
anything you left out. If no song was found for the language, say the film is silent until the
track is added to `assets/music/`.

## Music

`SKILL_DIR/assets/music/` holds one track per language, named by language code:
`en.mp3`, `de.mp3`, `ru.mp3` (also .m4a/.wav/.flac/.ogg). `--music <file>` overrides this.
