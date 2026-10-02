# Team headshots

The Masthead (/team/) reads every person from `data/team.json`; each entry's
`photo` field names its file here (for example `"/assets/team/noah.jpg"`), and
`null` shows the person's initials in the card's photo window instead.

- Format: square JPEG, 600 x 600, RGB (no alpha), progressive. The card's photo
  window crops it with `object-fit: cover`, framed a little above centre.
- Processing a new photo: crop to a square around the face, resize to 600 x 600
  with Lanczos resampling, flatten any alpha, save as JPEG (quality about 90).
- A file is only shown when it exists, so a missing photo never draws a broken
  image.

Note: these must be images the person is OK publishing. We do **not** pull photos
from LinkedIn: that violates LinkedIn's terms and their image URLs are signed and
expire. Ask each person for a headshot to drop in here.
