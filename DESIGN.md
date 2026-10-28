---
version: alpha
name: Media Downloader
description: A calm Thai personal media-saving workspace inspired by a desktop download tray.
colors:
  primary: '#245bcc'
  background: '#eef3f9'
  surface: '#ffffff'
  text: '#172942'
  muted: '#52657d'
  border: '#d6e0ed'
  danger: '#a12b38'
  success: '#216344'
typography:
  sans:
    fontFamily: 'Segoe UI, Tahoma, sans-serif'
rounded:
  DEFAULT: '6px'
  panel: '12px'
spacing:
  unit: '8px'
  page-max: '1080px'
components:
  button: {}
  input: {}
  progress: {}
---

# Media Downloader Design System

## Overview

### Creative North Star
A desktop download tray: one link goes in, a clear set of files comes out.

### Product context and register
Personal localhost tool for a Thai-speaking owner, based on the user's project brief.
One screen for URL inspection, mixed-media selection and asynchronous download.
Thai locale; no Japan-market requirements. Desktop-first with full mobile support.
The signature is a three-stage path and an open media-selection list. No marketing
sections, invented metrics, decorative dashboard chrome or external font requests.
Runtime ownership is Model B: `frontend/styles.css :root` owns semantic tokens;
this document mirrors them. `--color-*` supplies all component colors,
`--radius-*` supplies controls/workspace, `--font-*` supplies typography,
`--space-unit` and `--page-max` define rhythm and outer geometry.
No sibling screen exists; all states share the same workspace.

## Colors
Cool blue-gray background, white workspace, navy text and cobalt primary action.
Muted text remains legible. Danger means actionable error; success is reserved for
completion. Visible scrollbar thumb uses the shared blue-gray scale. Forced-color
mode restores system colors. Only a light theme is implemented.

## Typography
Segoe UI display, 30px/1.3 bold; Segoe UI/Tahoma body, 16px/1.65. Thai-capable
system fallbacks avoid font-loading shifts. Help is 14px and footnotes 12–13px.
Long source titles wrap. Numeric formatting uses th-TH; duration uses minutes and seconds.

## Layout
1080px maximum page width, 24px outer gutters, 30px workspace padding.
At 640px controls and preview stack. Document owns vertical scrolling. Progress,
thumbnail aspect ratio and error slot reserve geometry. There is no fixed-height
application shell or nested vertical scroller.

## Elevation & Depth
Flat white workspace with a single border. No nested cards or decorative shadows.
Progress uses a quiet blue-gray surface to show its relationship to the download.

## Shapes
6px controls and thumbnail frames; 12px workspace; circular step counters.
Native checkbox and select geometry is explicitly accepted, including OS popup style.

## Components
Buttons use solid primary or neutral outline, at least 48px high, stable busy width,
visible focus and disabled semantics. Labels, inputs and help own the URL form.
Media checkboxes and the select-all checkbox own selection; the latter has an
indeterminate state. Native select owns quality choice and its popup.
One inline alert owns errors; the job status live region owns asynchronous feedback.
No modal or toast system is necessary. Global CSS owns scrollbar behavior.
The download-arrow mark is inline SVG; no production bitmap asset is required.
No decorative animation; reduced motion disables any future transitions.
All user-visible messages and accessible names are Thai, apart from platform names,
standard formats and product name.

## Do's and Don'ts
- Do preserve selected choices on recoverable errors and disable duplicate submissions.
- Do use textContent for extractor-provided titles and backend-proxied thumbnails.
- Do show unknown progress as indeterminate, and provide a file link after completion.
- Don't put source URLs or browser cookies in browser storage; only a job ID is persisted in sessionStorage.
- Don't imply that a private, DRM or paywalled post is supported.
