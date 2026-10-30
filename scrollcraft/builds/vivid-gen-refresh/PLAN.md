# Vivid Gen | art direction and implementation plan

## Page grammar: Director's Contact Sheet (new, product-specific)

The site opens on a human creator portrait with a floating sample production brief and frame preview. The header is a quiet studio index with direct jumps to the studio and bundles. A light studio-process section bridges the hero and a three-card Creator / Studio / Agency bundle lineup; the closing action carries the active sample prompt into the existing create route.

**Explicit bans:** no invented testimonial quotes, fake scarcity counts, unsupported pricing, repetitive icon/card grids, full-screen autoplay video, or long feature paragraphs. Animation is used as a quiet production mark, not ambient confetti. The existing public pages remain ordinary accessible Next.js content; the product sample is labelled as a preview.

## Signature move: Brief-to-plan lens

Changing between Product launch, Creator story, and Campaign film updates the sample brief and its scene title in place, preserving the same visual frame while the preview re-labels. The selected sample prompt is carried into the create route.

## Fingerprint gate

The workspace registry was empty before this build. With no existing rows, no comparison gate is triggered. The row will be appended after the final visual review.

## Hero layer contract

| Plane | Treatment | Movement | Relationship |
|---|---|---|---|
| Far environment | Dark canvas, restrained red light falloff | Very slow scroll response | Remains behind type and photography |
| Photographic subject | Real creator/collaboration still | Moderate scroll and hover shift | Keeps the people and scene intact |
| Prompt surface | Small floating translucent brief card | Workflow selector changes sample brief and frame label | Overlaps the image edge, never covers the person’s face |
| Frame preview | Compact image within brief panel | Hover scale, selected scene title | A shallow second plane within the brief surface |
| Lottie accents | Camera and spark accents from LottieFiles | Looped subtly; CSS reduced-motion stop | Decorative only; color-filtered to the warm red palette |
| Type and controls | Semantic HTML | Stable | Headline and actions remain clear at every viewport |

Opening: one human moment, with the brief-to-plan preview already legible.
Midpoint: workflows and curated bundles clarify the available paths.
Exit: one featured route to sign-up/create, no fake timer or capacity counter.

## Mobile composition

At 760px and below, keep the creator image behind the copy and move the brief into a stable lower column. Stack the studio image and explanation, then stack the bundles. Keep selectors touch friendly and retain the full static composition under reduced motion.

## Visual score

1. Recognition: natural-flow layered photo hero, no video dependency.
2. Curiosity: bespoke Brief-to-plan lens within the hero.
3. Clarity: three compact studio steps.
4. Range: three curated service bundles, with the Studio option featured.
5. Commitment: resolved signup action panel.

Devices are chosen to match this compact product-showcase grammar: natural flow, reveal, independent hero planes, and a responsive bundle grid. The Lottie accents are UI animation, not scroll devices.
