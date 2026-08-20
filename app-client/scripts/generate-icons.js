/**
 * Generate placeholder app icon and splash screen images.
 *
 * Requirements:
 *   npm install --save-dev sharp
 *
 * Usage:
 *   node scripts/generate-icons.js
 *
 * This creates simple placeholder images. Replace them with real branding
 * assets before App Store submission.
 *
 * Required files:
 *   assets/icon.png          — 1024x1024  (App Store icon)
 *   assets/adaptive-icon.png — 1024x1024  (Android adaptive icon foreground)
 *   assets/splash.png        — 1284x2778  (Splash screen)
 *   assets/favicon.png       — 48x48      (Web favicon)
 */

const fs = require('fs');
const path = require('path');

// Simple 1x1 PNG generator (no dependencies needed)
// Creates a solid-color PNG with text overlay
function createMinimalPNG(width, height, r, g, b) {
  // Minimal valid PNG: IHDR + IDAT (uncompressed) + IEND
  // For placeholder purposes, we create a very small image and note
  // that real icons should be designed properly.

  // Use a data URI approach — write a simple SVG and note it needs replacement
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="${width}" height="${height}" fill="rgb(${r},${g},${b})"/>
  <text x="50%" y="45%" text-anchor="middle" fill="white" font-size="${Math.floor(width * 0.15)}" font-family="Arial, sans-serif" font-weight="bold">🌳</text>
  <text x="50%" y="65%" text-anchor="middle" fill="white" font-size="${Math.floor(width * 0.06)}" font-family="Arial, sans-serif">BigTree</text>
</svg>`;
  return svg;
}

const assetsDir = path.join(__dirname, '..', 'assets');
fs.mkdirSync(assetsDir, { recursive: true });

// Write SVG placeholders (Expo will need PNG — see instructions below)
const configs = [
  { name: 'icon.svg', w: 1024, h: 1024 },
  { name: 'adaptive-icon.svg', w: 1024, h: 1024 },
  { name: 'splash.svg', w: 1284, h: 2778 },
  { name: 'favicon.svg', w: 48, h: 48 },
];

for (const c of configs) {
  const svg = createMinimalPNG(c.w, c.h, 15, 20, 25); // #0F1419
  const outPath = path.join(assetsDir, c.name);
  fs.writeFileSync(outPath, svg, 'utf-8');
  console.log(`Created ${c.name} (${c.w}x${c.h})`);
}

console.log(`
============================================================
  SVG placeholders created in assets/

  IMPORTANT: Expo requires PNG files, not SVG.
  Convert these to PNG before building:

    1. Open each SVG in a browser and screenshot, OR
    2. Use an online converter (svg2png), OR
    3. Install 'sharp' and convert programmatically:
       npx sharp -i assets/icon.svg -o assets/icon.png
       npx sharp -i assets/adaptive-icon.svg -o assets/adaptive-icon.png
       npx sharp -i assets/splash.svg -o assets/splash.png
       npx sharp -i assets/favicon.svg -o assets/favicon.png

  For App Store submission, replace these with professionally
  designed branding assets.
============================================================
`);
