# Browser theme alignment — 2026-09-26

## Scope and decisions

Bring the existing browser pages into the React Native app’s cocoa, cream and
rose visual language. Keep the existing page content, account flows and report
workflows. Reuse the shared `styles.css` rather than introducing another web
framework or theme system.

- Browser palette and typefaces follow `apps/mobile/src/ui/theme.ts`: Work Sans
  for body text, Newsreader for headings, cream surfaces, cocoa actions and rose
  accents. Existing DM Mono labels remain.
- Cards, form fields and buttons use the native app’s softer corner treatments.
  Text and placeholders use readable theme colors; links and buttons have visible
  keyboard focus. Input text is 16px for comfortable phone entry.
- Warm control borders are slightly deeper than the native token so white,
  cream and blush surfaces retain at least 3:1 boundary contrast.
- Every browser page has 22 decorative falling petals: six pastel yellow,
  six pastel blue, six pastel pink and four light brown. Existing trajectories
  remain, with staggered positions and timings for the additional petals.
  The shared decorative layer is hidden from accessibility tools, ignores pointer
  input and uses a single opacity to keep overlaps from darkening behind text.
- Reduced-motion styling stops the petals and interactive lift transitions.
- Narrow headers wrap instead of overflowing the screen.

## Verification

Locally verified on sign-in, activation/recovery, crew, manager, accounts,
inventory and about pages:

- Initial 28 rendered page/viewport checks at 320, 768, 1024 and 1440 CSS pixels:
  no horizontal overflow. After the petal-count revision, all seven HTML pages
  were checked for exact 6/6/6/4 counts; the refreshed crew preview confirmed
  all 22 petals, four colors and the existing animation.
- Desktop and narrow-phone visual review, loaded Work Sans/Newsreader fonts,
  keyboard focus, and the account connection-error state.
- 13 foreground/background contrast checks: normal text at least 4.5:1 and
  control borders at least 3:1. Reduced-motion CSS and noninteractive decoration
  were inspected in the rendered stylesheet.
- Parsed HTML comparison against the starting revision confirms unchanged body
  content, form controls, IDs, scripts and links outside the decorative layer.
- Independent bounded HTML/CSS review and `git diff --check` passed.

The preview uses synthetic responses and rejects writes. No application database
was used for visual verification. No backend or native test suite was rerun for
these presentation-only changes. This record describes local implementation and
verification; it does not represent a commit, CI result or hosted deployment.
