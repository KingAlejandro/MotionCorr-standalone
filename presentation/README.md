# Motion, corrected.

A 3-minute hackathon film for STFC, Google and PA.

## Watch and edit

Open `preview.html` in a modern desktop browser. It is a portable, offline review player with Play/Pause, a timeline, a caption toggle, fullscreen, and a local voiceover file picker. Space toggles playback; arrow keys move five seconds. Fonts use locally installed Inter or Arial. No font binaries are included.

The delivered MP4 is 1920 × 1080, 30 fps, exactly 180 seconds. Subtitles are burned into the picture. The soundtrack is an original, programmatically synthesised instrumental cue. There is no generated voiceover in this version.

`index.html` is the editable composition source. Its timeline is paused by design and exposes `window.seekFilm(seconds)`. Use `preview.html` for playback, rather than opening the paused source.

## Contents

- `source/story.json`: scene boundaries and timed narration cues.
- `narration.md`: the 379-word narration, divided by scene, ready for a future voiceover.
- `subtitles.srt` and `subtitles.vtt`: editable subtitle sidecars.
- `DESIGN.md`: visual identity, layout and motion rules.
- `SOURCES.md`: provenance, scope qualifications, and the repository review index.
- `assets/`: original synthetic microscopy illustrations, the original instrumental score, and the supplied animation library.
- `source/`: composition generator, deterministic capture script, preview generator and audio/image generation scripts.
- `review/`: representative frames and layout-check results.

The microscopy is an explicitly labelled synthetic illustration. The agent dialogue and workspace are dramatisations, not transcripts or screenshots of an actual application session. Performance figures are labelled by stage, workload and evidence status. The preliminary reconstruction figure is not a claim of whole-pipeline speedup or completed scientific validation.

## Update the text or visuals

Edit `source/story.json` for narration and timing. Scene design and animation are in `source/build_film.py`. After a change:

```sh
python source/build_film.py
python source/make_preview.py
python source/inspect_film.py
```

The narration word-count line is currently written for this 379-word cut; update it in `source/build_film.py` when changing the script substantially. Keep the film duration at 180 seconds, or change the duration consistently in the story, composition and player.

## Render locally

This composition uses HTML/GSAP with Hyperframes-compatible timing attributes and a registered root timeline. The delivered picture was captured from the deterministic timeline using Chromium and encoded with FFmpeg. The full uploaded Hyperframes engine source is not duplicated in this project.

Requirements: Python 3.10 or later, FFmpeg, and Chromium. Python dependencies:

```sh
python -m pip install playwright pillow numpy scipy
```

A system Chromium installation is detected automatically. Alternatively install the browser managed by Playwright:

```sh
python -m playwright install chromium
```

Render and add the music:

```sh
python source/render_film.py --output renders/picture.mp4 --workers 3
ffmpeg -i renders/picture.mp4 -i assets/original-score.m4a \
  -map 0:v:0 -map 1:a:0 -c:v copy -c:a copy \
  -t 180 -movflags +faststart renders/motioncorr-final.mp4
```

Use `--clean` to render a picture without burned-in subtitles. `--duration 10` produces a short test. `--chromium /path/to/chromium` selects a specific browser. Rendering loads the composition in memory and does not require a local web server.

## Add a voiceover later

Use the timings in `source/story.json` and `subtitles.srt`. A continuous narration recording should be aligned to start at 00:00, including the intended pauses. The preview player's **Load voiceover** button auditions a local audio file; it does not upload it or modify the MP4. It lowers the music in the preview automatically.

To export with an aligned narration file named `narration.wav`:

```sh
ffmpeg -i renders/picture.mp4 -i narration.wav -i assets/original-score.m4a \
  -filter_complex "[1:a]apad,atrim=0:180[v];[2:a]volume=0.38[m];[v][m]amix=inputs=2:duration=longest:normalize=0[a]" \
  -map 0:v:0 -map "[a]" -c:v copy -c:a aac -b:a 192k \
  -t 180 -movflags +faststart renders/motioncorr-with-voice.mp4
```

Check intelligibility and synchronisation before screening. A newly generated voice may require small scene or caption timing changes rather than forcing a rushed read.

## Rebuild the original assets

`python source/make_assets.py` regenerates the seeded synthetic microscopy illustrations. `python source/make_music.py` regenerates the original 180-second stereo WAV score. The WAV is omitted from the package to keep it small; its compressed M4A is included.

```sh
ffmpeg -i assets/original-score.wav -c:a aac -b:a 192k assets/original-score.m4a
```

## Third-party notice

`assets/gsap.min.js` is GSAP 3.15.0, copied from the supplied Hyperframes archive. Its original copyright and licence notice is preserved in the file. Consult that notice and the applicable GSAP licence for reuse. No fonts, stock recordings or external image libraries are bundled.
