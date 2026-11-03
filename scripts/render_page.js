// HTML renderizado de uma página que monta o texto por JavaScript (o fetch estático devolve a casca vazia).
// Uso: node scripts/render_page.js <url>  → HTML no stdout. Chromium e Playwright vêm no ambiente da nuvem.
// Espera o DOM e mais alguns segundos (não "networkidle": rastreadores do site nunca deixam a rede quieta).
const { chromium } = require('playwright');

(async () => {
  const url = process.argv[2];
  const waitMs = Number(process.env.RENDER_WAIT_MS || 5000);
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ userAgent: 'Mozilla/5.0 (support-agents ingest)' });
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(waitMs);
    // Tira o que é moldura do site (menu, cabeçalho, rodapé, aviso de cookie, janela de "já é cliente?"): no HTML
    // estático o ingest tira isso como linha repetida entre páginas; renderizado, viria grudado no 1º trecho.
    await page.evaluate(() => {
      const chrome = 'header, nav, footer, [role="dialog"], [aria-modal="true"], [id*="cookie" i], '
        + '[class*="cookie" i], [class*="consent" i], [id*="onetrust" i], [class*="modal" i]';
      document.querySelectorAll(chrome).forEach((el) => el.remove());
    });
    process.stdout.write(await page.content());
  } finally {
    await browser.close();
  }
})().catch((err) => { console.error(String(err).slice(0, 300)); process.exit(1); });
