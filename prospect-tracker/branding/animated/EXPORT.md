# Animated mark, export notes

The in-site source of truth is CSS. The homepage hero plays the pitch once on
load (the vector draw-on today; the pixel pitch of `assets/brand/wordmark.css`
when `build_site.py`'s `PIXEL_BRAND` flag is on). Nothing animated ships as a
raster into the running site. These exports are for sharing (social, decks,
README embeds).

## What the generator writes

`python tools/pixel_brand.py` writes, from `tools/pixel_brand_src.py`, the pitch
at s 8 (the half-u arc and the 32 px ball, padded 3 u for the drop):

- `eephus-arc.svg` and `eephus-arc-dark.svg`: self-contained, with their own
  CSS and raw hex. The arc lights run by run, then the ball drops in four
  whole-pixel frames. `step-end` only, one play, no script; the base style is
  the finished mark, so a viewer that runs no CSS animation shows the static
  mark. Works as an `<img>`, an `<object>` or inlined.
- `frames/frame_000.png` ... a transparent PNG frame sequence (dark theme), one
  frame every 40 ms; the last frame is the finished mark. This is the export
  source for a crisp alpha video.
- `eephus-arc.gif`: the same frames matted on the dark field colour (`#0C0C0E`),
  since GIF only does one-bit transparency. Exact palette, no dither. It plays
  once and holds the finished mark (no loop).

## The format tradeoff

For a clean transparent animation, use WebM or MP4 with an alpha channel, not GIF.
The frame sequence is the source (25 frames per second is the 40 ms spacing).
ffmpeg is not installed on the build box, so run these by hand on a machine that
has it:

WebM with alpha (VP9):

    ffmpeg -framerate 25 -i frames/frame_%03d.png \
      -c:v libvpx-vp9 -pix_fmt yuva420p -b:v 0 -crf 28 eephus-arc.webm

MP4 with alpha (HEVC, Safari / Apple):

    ffmpeg -framerate 25 -i frames/frame_%03d.png \
      -c:v hevc_videotoolbox -alpha_quality 0.9 -tag:v hvc1 eephus-arc.mp4

Keep the pixels: scale only by whole numbers with nearest neighbour (ffmpeg
`-vf scale=iw*2:ih*2:flags=neighbor`), never a smoothing filter.

Static fallback (favicons, anywhere motion does not belong): the last frame in
`frames/`, or the static marks in `../marks/`.
