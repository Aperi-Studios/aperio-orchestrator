# Motion doctrine: building product videos with agents

> **For agents.** When the owner asks for a product launch video, motion
> graphic, or animated demo, follow this page. It is distilled from an
> audit (2026-10-29) of the NullMotion ecosystem — NullMotion itself, the
> HyperFrames render substrate, and the html-anime motion doctrine — with
> sources cited at the bottom. The doctrine maps onto Aperio's gates:
> the shot sheet is the plan; the determinism contract is the bounds;
> lint/validate is the acceptance gate.

## 1. Know the tools (research findings, 2026-10-29)

- **NullMotion** (blixvip/NullMotion, MIT, 1.2k stars) is a *study viewer*,
  not a video maker: it plays a finished ad in sync with hand-drawn B&W
  rough drafts and exports the breakdown as MP4. Its showcase ads were made
  by other creators. It does not generate videos and contains no SKILL.md.
- **HyperFrames** (heygen-com/hyperframes, Apache-2.0, 75k stars,
  HeyGen-backed) is the real substrate: "Write HTML. Render video. Built
  for agents." HTML/CSS/GSAP compositions declared via a meta tag, rendered
  to deterministic MP4 with `npx hyperframes render`. Requires Node ≥ 22.
- **html-anime** (blixvip/html-anime, MIT) carries the quality doctrine:
  five SKILL.md files (direct, cel, timing, camera, render) with
  machine-checkable done-criteria.
- **The honest warning:** the impressive demo videos attached to these
  projects are third-party footage or hand-tuned one-offs. The *doctrine*
  is real; the "type an idea, get a launch film" story does not exist yet
  anywhere in this ecosystem.

## 2. The shot sheet is the plan (Define gate)

**"The sheet is the film. Draw only after it exists."**

Before any animation code:

1. Write a one-line logline for the video.
2. Produce a shot sheet: 8 / 12 / 20 seconds total, split into scenes with
   exact times that **sum to the runtime** (checked, not asserted).
3. Exactly one expensive "sakuga" shot — the single moment the video is
   remembered for. Everything else is cheaper support.
4. A closed color script: only hexes printed on the sheet. No colors
   invented at build time.
5. Loop structure: hook → establish → proof → button. The button shot
   lands in the last 2 seconds.

The owner approves the sheet before any build. Adding shots, colors, or
moods not on the sheet is scope expansion — same rule as code plans.

## 3. The determinism contract (bounded execution)

Agent-built animation must be reviewable frame-by-frame, which requires
determinism:

- One paused GSAP timeline registered at `window.__timelines.root`, built
  synchronously — no `async`, no `setTimeout`, no `Promise`.
- **No `Math.random()`, no `Date.now()`.** Rain, particles, noise: written
  out literally or from a seeded sequence.
- Animate only `transform`, `opacity`, `color`, and `stroke` — properties
  the renderer can composite deterministically.
- Fonts ship as local `.woff2`; never rely on system fonts.
- Declare the composition in the document head:
  `<meta name="hyperframes" content="duration:4,fps:30,width:1920,height:1080">`.

## 4. Timing discipline (the quality is in the holds)

- 24 fps for character work, acting **on twos** (each drawing holds two
  frames); effects on ones.
- **Sakuga budget:** the expensive shot gets 8 unique drawings; supporting
  shots get 3.
- **≥ 12-frame hold after every settle.** Motion that never rests reads as
  noise.
- Anticipation: 4 frames the other way before a main movement.
- Real smear frames for fast motion — "not a CSS blur standing in for the
  smear."
- No opacity-0 fade-ins for characters; enter with a drawn reason.

## 5. Easing and motion vocabulary (measured from the good examples)

- Entrances: `power4.out` / `power3.out`; reveals with overshoot:
  `back.out(1.3–2)`; type-on with `clipPath: inset()` wipes and `steps()`
  for typing; idle drift at `sine.inOut`, 2–4% scale drift over a scene.
- Word-level stagger of 0.04–0.15s on headline reveals.
- Masked word reveals: `overflow:hidden` word masks, x ± 112px entrance
  with `blur(8px)` and slight rotation.
- 3D depth via `translateZ` planes (atmosphere at −160px, orbit at −90px).
- Cuts are **color dips**, not fades: 0.25s `power2.in` to the cover color,
  0.35s out.
- One camera move per film, if any: a 100%→106% scale at `power1.inOut`.

## 6. Acceptance gate (machine-checkable)

A build is not done because it looks right once. The done-criteria:

1. `npx hyperframes lint` passes.
2. `npx hyperframes validate` passes.
3. Shot times sum to the declared runtime (checked by a test, not an
   assertion in prose).
4. No `Math.random()` / `Date.now()` / `async` in the composition source
   (greppable).
5. The human watches the preview (`npx hyperframes preview`) before
   "finished" — the independent-review gate.

## 7. Rendering (ship gate)

`npx hyperframes render` produces the deterministic MP4. Browser-side
export (WebCodecs, the NullMotion pattern) exists but is Chrome/Edge-only
and takes ≥ 2× runtime; prefer the renderer. Aperio does not run the
renderer itself — the plan declares the render command, the run executes
it, and the acceptance gate checks the output file exists and matches the
declared duration/fps.

## 8. Aperio mapping

| Motion workflow | Aperio gate |
|---|---|
| Shot sheet (times sum, one sakuga, closed palette) | plan gate — the sheet IS the plan |
| Owner approves the sheet | approval gate |
| Determinism contract (paused timeline, no random) | bounded execution |
| `lint && validate`, times-sum check | acceptance checks |
| Human watches the preview | independent review |
| `hyperframes render` | ship (declared command, owner runs it) |

## 9. Sources

- NullMotion: https://github.com/blixvip/NullMotion (study viewer; drafts in
  `public/drafts.mjs`; exporter in `public/demo.mjs`; section planner in
  `scripts/plan-sections.mjs`)
- html-anime doctrine: https://github.com/blixvip/html-anime — five SKILL.md files under `skills/` in that repository (html-anime-direct, html-anime-cel, html-anime-timing, html-anime-camera, html-anime-render)
- HyperFrames: https://github.com/heygen-com/hyperframes
- Audit date: 2026-10-29. NullMotion is six weeks old with a single
  active maintainer; re-verify health before building on it.
