const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const FPS = 30;
const LOOP_SECONDS = 15;
const TOTAL_FRAMES = FPS * LOOP_SECONDS;
const FRAMES_DIR = path.join(__dirname, 'frames');
const SCENE_URL = 'file:///' + path.join(__dirname, 'yt_scene.html').replace(/\\/g, '/');

(async () => {
  fs.rmSync(FRAMES_DIR, { recursive: true, force: true });
  fs.mkdirSync(FRAMES_DIR);

  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  await page.goto(SCENE_URL, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => {
    const img = document.querySelector('img');
    return img && img.complete && img.naturalWidth > 0;
  });

  // Congela as animações e posiciona cada quadro manualmente — captura
  // determinística, independente da velocidade da máquina.
  await page.evaluate(() => document.getAnimations().forEach((a) => a.pause()));

  for (let i = 0; i < TOTAL_FRAMES; i++) {
    const ms = (i * 1000) / FPS;
    await page.evaluate((t) => document.getAnimations().forEach((a) => { a.currentTime = t; }), ms);
    await page.screenshot({ path: path.join(FRAMES_DIR, String(i).padStart(4, '0') + '.png') });
    if (i % 90 === 0) console.log(`frame ${i}/${TOTAL_FRAMES}`);
  }

  await browser.close();
  console.log('ok', TOTAL_FRAMES, 'frames');
})();
