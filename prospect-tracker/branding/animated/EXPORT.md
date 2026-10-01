# Animated mark, export notes

The in-site source of truth is CSS. The masthead lockup plays the animation on
load (`.eephus-logo--animate` in `assets/site.css`); `eephus-arc.svg` here is the
self-contained standalone version. Nothing animated ships as a raster into the
running site. These exports are for sharing (social, decks, README embeds).

## What the generator writes

`python tools/generate_brand_assets.py` writes:

- `frames/frame_000.png` ... a transparent PNG frame sequence. This is the export
  source for a crisp alpha video.
- `eephus-arc.gif` a matted GIF. GIF only does one-bit transparency, so it carries
  a near-black (`#0C0C0E`) matte instead of real alpha. Use it where a GIF is the
  only option and the background is dark.

## The format tradeoff

For a clean transparent animation, use WebM or MP4 with an alpha channel, not GIF.
The frame sequence is the source. ffmpeg is not installed on the build box, so run
these by hand on a machine that has it:

WebM with alpha (VP9):

    ffmpeg -framerate 25 -i frames/frame_%03d.png \
      -c:v libvpx-vp9 -pix_fmt yuva420p -b:v 0 -crf 28 eephus-arc.webm

MP4 with alpha (HEVC, Safari / Apple):

    ffmpeg -framerate 25 -i frames/frame_%03d.png \
      -c:v hevc_videotoolbox -alpha_quality 0.9 -tag:v hvc1 eephus-arc.mp4

Higher-quality GIF than the committed one (palette pass), still matted:

    ffmpeg -framerate 25 -i frames/frame_%03d.png \
      -vf "palettegen=stats_mode=single" palette.png
    ffmpeg -framerate 25 -i frames/frame_%03d.png -i palette.png \
      -lavfi "paletteuse=dither=bayer" eephus-arc-hq.gif

Static fallback (favicons, anywhere motion does not belong):
the final frame, `frames/frame_041.png`, or the static marks in `../marks/`.
