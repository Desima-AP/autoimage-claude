# Prompt templates for auto-image

Load this only when the asset type doesn't fit the short rules in
`SKILL.md`, or when a generation comes back weak and you need to
re-engineer the prompt.

## The 5-component formula (refresher)

1. **Subject** — concrete visual
2. **Action / state**
3. **Location / context**
4. **Composition**
5. **Style** — medium + lighting + palette

Bake brand palette and mood into (5) for every asset.

## Per-domain templates

### Hero / banner (cinematic)

```
[Subject: concrete human or object, one clear focal point], [action verb]
in [location: time + atmosphere]. [Composition: rule-of-thirds, subject
on the left third, negative space on the right for headline copy].
Shot on [camera: Sony A7R IV / Canon EOS R5] with [lens: 35mm / 50mm]
at [f-stop: f/1.8 for shallow DOF]. [Lighting: golden-hour rim light /
cool overcast / studio soft key]. Colour palette anchored to
[primary hex] with accents of [accent hex]; overall [mood keyword,
e.g. editorial, confident, restrained]. Composition leaves at least
30% negative space on [left|right|top].
```

### Open Graph card (1200×630)

```
[Subject centred, simplified], set against [clean geometric backdrop
using primary hex #XXX]. [Optional: the text "EXACT COPY" in a
[typography description: modernist sans-serif, tight tracking]].
Flat composition, readable at thumbnail size (200×105 px), high
contrast between subject and background. Accent colour #XXX used
sparingly for emphasis. No busy detail — optimised for small-screen
social card rendering.
```

### Icon (single glyph, transparent)

```
A single [concept] glyph rendered as a flat vector mark. Clean
geometric construction, 2px equivalent stroke weight at 64px output
size. One-colour silhouette in [primary hex #XXX] on a plain neutral
background (will be made transparent). No text, no drop shadow, no
gradients beyond a single accent highlight. Centred composition with
even optical padding on all sides.
```

### Logo (brand mark)

```
A geometric brand mark for "[project name]". [Shape cue: a monogram
of the letter X / an abstract mark suggesting Y]. 3 colours maximum
from the palette: [primary #XXX], [secondary #XXX], [accent #XXX].
Clean vector construction, scalable from 16px favicon to 512px app
icon. Plain neutral background (will be made transparent).
Modernist sans aesthetic, no skeuomorphism, no photographic
elements.
```

### Avatar (portrait)

```
A [role: friendly engineer / founder / researcher], [age range],
[expression: warm half-smile / focused / confident], shoulders-up
framing. [Lighting: soft window light from the left / studio
three-point]. Blurred background in [secondary hex #XXX] tones, no
distracting detail. [Attire: smart-casual / technical sweater /
blazer]. Shot on [50mm / 85mm] portrait lens. Neutral, professional,
approachable — suitable for About page or team grid.
```

### Feature card (product-mode)

```
[Product or concept represented as an object], [displayed on a
clean studio surface / floating against a subtle gradient]. [Props
or supporting elements: minimal, 2–3 max, supporting the product
without crowding]. Colour palette anchored to [primary #XXX] surface
with [accent #XXX] as a single pop. Commercial photography feel,
4:3 landscape composition, room on the right for a short caption.
Soft key light from above-left, subtle rim highlight.
```

### Background (low-contrast atmospheric)

```
An abstract atmospheric background suggesting [mood adjective:
calm / energised / technical / editorial]. Soft gradient from
[primary hex] at the top-left to [secondary hex] at the bottom-right,
overlaid with [subtle texture: organic grain / geometric grid at 8%
opacity / diffuse particle field]. LOW CONTRAST — designed to sit
behind heading and body copy without competing. No focal subject,
no faces, no readable text. Wide aspect, seamless edges so it can
tile or fade off-screen.
```

### Illustrated (vector-style)

```
A [adjective] flat-vector [subject] in a [style: editorial / playful
/ technical] illustration style. Limited palette of 4 colours:
[primary hex], [secondary hex], [accent hex], [neutral hex]. Clean
geometric shapes, 2px equivalent linework, subtle cast shadows in
the accent colour at 30% opacity. Background is [colour] with no
pattern. Feels at home next to body copy on a modern SaaS
documentation page.
```

## Text-in-image prompts (use gpt-image-2)

gpt-image-2 renders text natively. Keep the copy under 25 characters and
quote it verbatim:

```
The text "EXACT PHRASE" rendered in a [font description: modernist
sans-serif, tight tracking, all-caps] in [primary hex #XXX],
positioned [top-left third / centred / bottom-right]. Supporting
[visual: minimal geometric shape, subtle gradient] in [accent hex
#XXX]. No other text, no lorem ipsum, no decorative script.
```

If the model misspells the text, re-run with the text inside **double
quotes + ALL CAPS**: `the text "SHIP FASTER"` tends to render more
reliably than lowercase.

## Safety rephrase strategies

When a generation is blocked:

| Blocked because | Rephrase strategy |
| :--- | :--- |
| Named public figure | Replace with role archetype: "a senior woman engineer in her 50s with silver hair" |
| Brand / trademark | Remove brand, keep category: "a premium athletic shoe" not "Nike Air Max" |
| Weapon, violence, explicit | Abstract the concept: "resolve" instead of "conflict resolution", "security" instead of "surveillance" |
| Minor + context | Replace with adult subject or remove the person entirely |
| Medical / scientific realism | Add "illustrated", "editorial", "conceptual" — moves out of literal territory |
| Political / news imagery | Reframe as generic civic scene without recognisable figures |

After rephrasing, run ONE retry. If it blocks again, report to the user
and ask how to proceed — don't keep guessing.

## When results are weak

Symptoms and fixes:

| Symptom | Likely cause | Fix |
| :--- | :--- | :--- |
| Muddy colours, washed-out | Palette absent from prompt | Add explicit hex values in the style component |
| Generic "AI look" | Prompt too abstract | Add concrete camera / lens / location details |
| Wrong aspect | Gemini crop mismatch | Set target dimensions, let post-process do the crop |
| Busy composition | Too many props | Say "single subject, negative space on the right" |
| Text garbled | Wrong provider for text | Re-route to gpt-image-2 (text-heavy rule) |
| Wrong mood | Brand mood not in prompt | Quote 2 of the `mood` array keywords in the style component |
