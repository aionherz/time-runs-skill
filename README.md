# Time runs fast

A free skill for **Claude** and **Codex** that turns your family photos and home videos into an
emotional music film in which you watch your children grow up.

- The AI looks at every photo and video, estimates the children's ages and puts everything in
  order, from the first days to today - for one child or for two or three siblings together.
- It marks the important area in every scene (the child with the balance bike, the cake, the
  hug), so the slow camera moves always settle on the children, never on an empty wall.
- It picks the liveliest moments from the videos (laughter, first steps, blowing out candles) and
  weaves them into the timeline.
- Soft transitions, a warm cinematic look, and a song by Aion Herz chosen by language
  (English, Deutsch, Русский). The photos and videos run exactly as long as the song, then a
  10-second closing card on white follows.
- Formats 9:16 (phone), 16:9 (TV), 1:1 and 4:5. Works on macOS, Windows and Linux.

Music: *Time runs fast* - Aion Herz - [aionherz.de](https://aionherz.de)
(the songs in English, Deutsch and Русский are included, about 1 minute each; with your own
song, pass `--music <file>`)

## Install

**Claude** - download [`time-runs-fast.zip`](time-runs-fast.zip) and upload it in Claude under
Settings → Skills.

**Codex** - copy the folder `time-runs-fast` into your skills folder:

```
git clone https://github.com/aionherz/time-runs-skill
cp -r time-runs-skill/time-runs-fast ~/.agents/skills/        # macOS / Linux
```

On Windows copy `time-runs-fast` to `%USERPROFILE%\.agents\skills\`.

On your own computer (Codex, Claude Code) you also need:

- Python 3.8+ with `pip install numpy pillow` (iPhone HEIC photos: `pip install pillow-heif`)
- ffmpeg - macOS `brew install ffmpeg`, Windows `winget install Gyan.FFmpeg`,
  Linux `sudo apt install ffmpeg`

Check everything with `python3 time-runs-fast/scripts/make_video.py --check`.

## Use

Attach photos and videos in the chat (or give the path to a folder) and ask, for example:

> Make a video of how our children grew up from these photos and videos. English, 9:16.

## License

Free for private use, may be modified and passed on free of charge - without any warranty.
See [`time-runs-fast/LICENSE.md`](time-runs-fast/LICENSE.md) (German, English, Russian) and
[`time-runs-fast/THIRD_PARTY_NOTICES.md`](time-runs-fast/THIRD_PARTY_NOTICES.md).

---

## Deutsch

Kostenloser Skill für Claude und Codex: macht aus Familienfotos und Heimvideos einen
emotionalen Musikfilm, in dem man die Kinder aufwachsen sieht - nach Alter sortiert, mit den
schönsten Momenten aus den Videos und einem Song von Aion Herz.

- **Claude:** `time-runs-fast.zip` herunterladen und unter Einstellungen → Skills hochladen.
- **Codex:** den Ordner `time-runs-fast` nach `~/.agents/skills/` kopieren; dazu Python mit
  `numpy` und `pillow` sowie ffmpeg installieren.
- Beispiel: *„Mach aus diesen Fotos und Videos einen Film, wie unsere Kinder aufgewachsen sind.
  Deutsch, 9:16."*

Kostenlos für die private Nutzung, Änderungen und kostenlose Weitergabe erlaubt, ohne Gewähr.

## Русский

Бесплатный скилл для Claude и Codex: превращает семейные фото и домашние видео в
эмоциональный музыкальный фильм о том, как растут дети - по возрасту, с лучшими моментами из
видео и песней Aion Herz.

- **Claude:** скачайте `time-runs-fast.zip` и загрузите в Настройках → Скиллы.
- **Codex:** скопируйте папку `time-runs-fast` в `~/.agents/skills/`; нужны Python с `numpy` и
  `pillow` и ffmpeg.
- Пример: *«Сделай из этих фото и видео фильм о том, как росли наши дети. Русский, 9:16.»*

Бесплатно для частного использования, можно изменять и бесплатно передавать дальше, без гарантий.
