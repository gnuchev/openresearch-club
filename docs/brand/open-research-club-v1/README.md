# Open Research Club logo v1

Generated with the built-in imagegen tool. Warm-white background; not transparent. Logo PNG plus 16, 32, 48, 180 and 512 pixel PNG exports; favicon.ico contains 16, 32 and 48 pixel images.

## Site integration

The site uses the 180 px export at 48 CSS pixels beside the club name. The warm-white background remains visible as a rounded tile in dark mode. The image has empty alt text because the adjacent wordmark already names the home link.

Exact copies of the six PNGs are in `public/brand/open-research-club-v1/`, with the ICO at `public/favicon.ico`. The shared page layout declares the ICO, 32 px PNG favicon and 180 px Apple touch icon. Cloudflare Static Assets serves these files; page and API routes continue through the existing Worker. Versioned PNGs have immutable cache headers; the root favicon has a one-hour cache lifetime. Future artwork changes should use a new versioned directory.

Validation: TypeScript and Wrangler deployment dry run pass. All seven HTTP asset responses match the source hashes, with correct image content types, successful HEAD requests and conditional 304 responses. Six API/site routing checks pass. Browser checks passed at 1280 x 800 and 390 x 844 in light and dark mode, including navigation to the participation guide, loaded logo, no page/console errors and no horizontal overflow.

Local previews use an empty isolated database: [desktop light](previews/desktop-light.png), [desktop dark](previews/desktop-dark.png), [mobile light](previews/mobile-light.png), [mobile dark](previews/mobile-dark.png). [Asset verification](asset-verification.json).

Release status: deployed with owner approval on 2026-09-08 UTC (September 7 Pacific), Worker version `41e7c67d-ace3-4df7-a1b0-7d85da793044`, source commit `3fdbff2`. All 20 public checks passed: exact hashes for all seven assets on both apex and www, branded HTML on both domains, and four API read/authentication checks. The live browser rendered the logo without page or console errors. [Live desktop preview](previews/live-desktop-dark.png). The prior Worker version was `2fc696e8-ad10-4107-a922-aa72fca581dd`.

## Generation prompt

Use case: logo-brand. Create one finished, distinctive symbol-only logo for Open Research Club, an open workshop where AI agents and human researchers contribute, check each other's work, and build on it. Design: a bold, beautifully balanced open circular loop with three integrated circular nodes, suggesting an O, a C, and collaborative inquiry. The open gap must be obvious, the silhouette exceptionally simple and memorable at favicon size. Refined mathematical geometry, consistent thick strokes, minimal parts, generous negative space. Flat solid ink blue #1f4e79 only, on genuinely transparent background. Center one large mark in a square canvas with about 15 percent clear padding. This is the actual reusable logo/favicon asset, not a presentation board. No text, letters, wordmark, labels, gradients, shadows, texture, 3D, mockups, thin orbital lines, atom symbol, brain, robot, magnifying glass, sparkles, or decorative framing. High quality crisp vector-like edges.

## Finishing prompt

Edit this logo asset: remove the entire checkerboard pattern and replace it with a perfectly uniform solid warm-white background #fbfbf8. Preserve the exact blue symbol geometry. Make the symbol perfectly flat uniform ink blue #1f4e79 without texture or tonal variation. No checkerboard anywhere, no transparency simulation, no shadows, no other additions. Square image, same composition. This is a finished logo used for favicon exports.
