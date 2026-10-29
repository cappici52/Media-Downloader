---
version: alpha
name: Media Downloader
description: A dark pixel-art media-saving utility with a white heterochromic cat.
colors:
  primary: '#80d8ed'
  background: '#101518'
  surface: '#1c2429'
  text: '#edf1eb'
  muted: '#a6b8c2'
  border: '#41545e'
  danger: '#ffadad'
  success: '#a9d7b1'
  picker-surface: '#182126'
  picker-tile: '#243138'
  picker-border: '#41545e'
  picker-text: '#edf1eb'
  picker-muted: '#a6b8c2'
  picker-accent: '#80d8ed'
typography:
  sans:
    fontFamily: 'Tahoma, Segoe UI, sans-serif'
rounded:
  DEFAULT: '0px'
  panel: '0px'
spacing:
  unit: '8px'
  page-max: '1040px'
components:
  button: {}
  input: {}
  progress: {}
---

# Media Downloader Design System

## Overview

### Creative North Star
A pixel desktop download tray: one link goes in, a clear set of files comes out.
User-approved direction: dark pixel art, white cat, blue left eye/gold right eye,
open mouth releasing image/video tiles, and a Thai/English language switch.

### Product context and register
Personal localhost tool for a Thai-speaking owner, based on the user's project brief.
One screen for URL inspection, mixed-media selection and asynchronous download.
Thai default with English switch; no Japan-market requirements. Desktop-first with full mobile support.
The signature is a three-stage path and a visual media picker. No marketing
sections, invented metrics, decorative dashboard chrome or external font requests.
Runtime ownership is Model B: `frontend/styles.css :root` owns semantic tokens;
this document mirrors them. `--color-*` supplies all component colors,
`--radius-*` supplies controls/workspace, `--font-*` supplies typography,
`--space-unit` and `--page-max` define rhythm and outer geometry.
No sibling screen exists; all states share the same workspace.

## Colors
Near-black charcoal background with a restrained 16px dotted pixel field, slate
workspace, cool white text and cyan primary actions. Gold is a small accent in the
cat's right eye and the decorative window rail. Colors mirror CSS `--color-*` and
`--picker-*`; `--color-on-primary` owns dark text on cyan buttons. Muted labels
remain legible. Danger means actionable error; success is reserved for completion.
The entire picker uses the same dark family as the main workspace. Forced-color
mode restores system colors. Pixel imagery applies to the brand, never to source
photos and videos.

## Typography
Self-hosted Silkscreen Regular owns the Latin wordmark and step numbers. Its OFL
license ships beside the font. Thai and interface copy use Tahoma/Segoe UI system
fallbacks at 16px/1.65 for readable Thai marks and English. Display is 28px/1.35,
19px on narrow screens. Help is 14px; footnotes 12–13px. No external font requests.
Source titles/captions remain verbatim, including Thai titles in English mode.

## Layout
1040px maximum page width, 24px outer gutters, 30px workspace padding.
At 640px controls and preview stack. Document owns vertical scrolling. Progress,
thumbnail aspect ratio and error slot reserve geometry. The application shell
is natural height. The modal body scrolls with its header and Done button kept
reachable. Its grid uses four columns on desktop, two below 640px. Tiles crop
square thumbnails; the expanded viewer contains the complete image or video.

## Elevation & Depth
One slate workspace with a 2px border and hard 6px offset shadow. Buttons use
hard 3px shadows; pressed controls move 2px. No rounded wrappers or soft glow.
Progress uses segmented cyan blocks on a dark track.

## Shapes
Square controls, thumbnail frames, workspace, dialog and step counters. Pixel
grid geometry remains crisp at small favicon and larger empty-state sizes.
Native checkbox and select geometry is explicitly accepted, including OS popup style.

## Components
Buttons use solid primary or neutral outline, at least 48px high, stable busy width,
visible focus and disabled semantics. Labels, inputs and help own the URL form.
Media checkboxes and the select-all checkbox own selection; the latter has an
indeterminate state. Native select owns quality choice and its popup.
One inline alert owns errors; the job status live region owns asynchronous feedback.
The native HTML dialog owns the media picker: showModal makes the background
inert and traps focus. Escape, backdrop, Close and Done dismiss it and restore
focus to the opener. `--z-dialog` owns its layer. Closing stops playback and
releases the stream. Thumbnail buttons expand/play; checkboxes alone change
selection. Native selects own quality; native video controls own playback.
Global CSS owns scrollbar behavior. No toast system is necessary.
The canonical `frontend/cat.svg` owns the header logo, empty state and favicon.
The viewer-left eye is blue, viewer-right gold; open mouth releases photo/video
rectangles. The user's supplied crop is the character reference: sitting fluffy
white cat, curled tail, pink open mouth, landscape tile and blue play tile.
`frontend/cat-reference.png` is the transparent production sprite generated from
that reference. `cat.svg` embeds that unchanged PNG with a content-bound viewBox,
so all three surfaces share one self-contained image and the existing asset route.
Desktop header is 88×64px, empty state 184×120px; mobile uses 64×48 and 160×104px.
The icon URL carries `?v=2` to refresh browser favicon caches. A generated full-screen
concept established the original visual direction.
No decorative animation; reduced motion disables any future transitions.
`frontend/i18n.js` owns Thai/English UI copy, dynamic counters/status templates,
accessible labels, placeholders and document title. Static leaf copy is marked
`data-i18n`; runtime copy binds canonical Thai sources to existing text/attribute
nodes. Switching updates those bindings without re-rendering checkboxes, quality
selects or video elements. Selection, progress, playback and keyboard focus survive.
Unknown Thai backend messages get a readable English access/retry fallback; known
backend messages use specific translations. Source titles and captions are never
translated. Header and modal each expose a language switch, because the header is
inert while the modal is open. Only `media-language` is stored in localStorage;
no source URL or credentials are stored. Default Thai is restored if storage is
blocked or the preference is invalid.

## Do's and Don'ts
- Do preserve selected choices on recoverable errors and disable duplicate submissions.
- Do use textContent for extractor-provided titles and backend-proxied thumbnails.
- Do show unknown progress as indeterminate, and provide a file link after completion.
- Don't put source URLs or browser cookies in browser storage; only a job ID is persisted in sessionStorage.
- Private posts require the user's own authenticated browser session with access granted by the provider. Never imply DRM or paywall bypass is supported.

## Instagram profile selection

The existing URL form and `renderMedia` picker own profile discovery. Profile cards
reuse preview buttons, checkboxes, focus rings and the dark grid. Each card shows
a cover, caption and media count. Opening a cover inspects the individual post;
return restores selected posts and focus. Native quality selects remain canonical
for individual posts. Profile ZIP downloads prefer video up to 720p.

Pagination uses Load more or Read all posts, with Stop. Partial results and
selections survive errors and retries. A new URL cancels requests and stale
responses cannot replace it. Empty results explain possible access restrictions.
Read all is bounded to 1,000 posts/100 pages. Aggregate media and byte limits
still apply per download. Existing alerts, progress and job recovery stay shared.

TikTok single video/photo posts reuse the same URL form, media picker, native
quality control, preview and download states. Slideshow soundtracks are omitted
from video selections. Unsupported LIVE links receive a Thai error. TikTok profiles reuse the canonical
profile grid, pagination, selection restoration and bulk ZIP flow. Platform names
come from profile metadata; completion copy remains platform-neutral.

Read-only inspection retries a busy worker slot for up to 20 seconds when profile
thumbnails occupy the shared pool. Abort and stale-response protections remain
active. Download creation never retries automatically.
