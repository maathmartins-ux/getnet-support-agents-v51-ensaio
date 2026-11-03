// Grava slides.html (uma "cena" por <section data-s="segundos">) em vídeo 1280x720 com o Playwright.
const { chromium } = require('playwright');
(async () => {
  const [,, html, outDir] = process.argv;
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 },
                                         recordVideo: { dir: outDir, size: { width: 1280, height: 720 } } });
  const page = await ctx.newPage();
  await page.goto('file://' + html);
  const durations = await page.$$eval('section', s => s.map(x => Number(x.dataset.s || 12)));
  for (let i = 0; i < durations.length; i++) {
    await page.evaluate(i => { document.querySelectorAll('section').forEach((s, k) => s.style.display = k === i ? 'flex' : 'none'); }, i);
    await page.waitForTimeout(durations[i] * 1000);
  }
  const video = page.video();
  await ctx.close();
  console.log(await video.path());
  await browser.close();
})();
