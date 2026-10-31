# Launchstation development instructions

## Adding fonts

- Every requested font style must independently provide all required characters:
  printable ASCII U+0020–U+007E and the Latin-1 supplement U+00A0–U+00FF.
- Check the source font's character map and render its glyphs with
  `scripts/gen_dash_font.py` before adding assets or build/menu entries. Space
  and nonbreaking space may be blank; other required glyphs must render.
- Do not fill missing characters using another font or introduce cross-font
  fallbacks. If any requested style lacks required characters, report the gaps
  and leave that font out unless the user explicitly changes this requirement.
