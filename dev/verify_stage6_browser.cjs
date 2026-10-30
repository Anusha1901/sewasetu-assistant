/* Isolated headless browser tests; never uses the user's profile or credentials. */
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const assert = require('node:assert/strict');
let playwright;
try { playwright = require('playwright'); }
catch (_) { playwright = require(path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')); }
const base = (process.argv[2] || 'http://localhost:8000').replace(/\/$/, '');
const tag = process.argv[3] || 'local';
const root = path.resolve(__dirname, '..');
const expected = JSON.parse(fs.readFileSync(path.join(root, 'app/evaluation/evidence.json'), 'utf8'));
const output = path.join(root, 'output/stage6'); fs.mkdirSync(output, {recursive:true});
const checks = [];
function check(name, ok) { checks.push({check:name,passed:!!ok}); console.log(JSON.stringify(checks.at(-1))); assert.ok(ok, name); }
(async () => {
  const exe = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
  const browser = await playwright.chromium.launch({headless:true, ...(fs.existsSync(exe)?{executablePath:exe}:{})});
  try {
    const context = await browser.newContext();
    const response = await context.request.get(base+'/eval-dashboard/evidence.json', {timeout:120000});
    check('public browser fetches evidence without authentication', response.status() === 200);
    assert.deepEqual(await response.json(), expected);
    check('served evidence exactly matches reviewed bundle', true);
    for (const viewport of [{width:1440,height:1000,name:'desktop'},{width:768,height:1024,name:'tablet'},{width:390,height:844,name:'mobile'}]) {
      const page = await context.newPage(); await page.setViewportSize(viewport);
      const errors = [], outside = [];
      page.on('pageerror', error => errors.push(error.name));
      page.on('request', request => { if (new URL(request.url()).origin !== new URL(base).origin) outside.push(request.url()); });
      await page.goto(base+'/eval-dashboard', {waitUntil:'networkidle', timeout:120000});
      check(viewport.name+' dashboard loads and has the required heading', await page.locator('h1').innerText().then(t=>t.includes('paper trail')));
      check(viewport.name+' has no horizontal document overflow', await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
      check(viewport.name+' displays both official endpoints', (await page.locator('.endpoint code').allTextContents()).length === 2);
      check(viewport.name+' renders all evidence scenarios', await page.locator('.scenario').count() === expected.scenarios.length);
      await page.keyboard.press('Tab');
      check(viewport.name+' keyboard reaches the visible skip link', await page.locator('.skip').evaluate(el=>document.activeElement===el && el.getBoundingClientRect().top >= 0));
      await page.locator('#scope-filter').selectOption('NOT TESTED');
      check(viewport.name+' scope filter shows exactly three untested scenarios', await page.locator('.scenario:visible').count() === 3);
      await page.locator('#category-filter').selectOption('Security');
      check(viewport.name+' category and scope filters combine correctly', await page.locator('.scenario:visible').count() === 1);
      await page.locator('#scenario-search').fill('no-such-evaluation-xyz');
      check(viewport.name+' empty search result is announced', await page.locator('#no-results').isVisible());
      await page.locator('#scope-filter').selectOption('all'); await page.locator('#category-filter').selectOption('all');
      await page.locator('#scenario-search').fill('competing');
      check(viewport.name+' text search finds the competing-decision scenario', await page.locator('.scenario:visible').count() === 1);
      await page.locator('.scenario:visible summary').click();
      check(viewport.name+' expanded scenario displays expected actual and evidence', await page.locator('.scenario:visible .comparison').isVisible() && await page.locator('.scenario:visible .assertions li').count() > 0);
      if (viewport.name==='mobile') await page.screenshot({path:path.join(output,tag+'-mobile-scenarios.png')});
      await page.locator('#scenario-search').fill('');
      await page.goto(base+'/eval-dashboard', {waitUntil:'networkidle'});
      if (viewport.name!=='tablet') await page.screenshot({path:path.join(output,tag+'-'+viewport.name+'-overview.png')});
      await page.locator('.source summary').first().click();
      check(viewport.name+' raw assertion list expands without a network API', await page.locator('.source[open] .assertions li').count() > 0);
      check(viewport.name+' no page script errors or third-party requests', errors.length===0 && outside.length===0);
      await page.close();
    }
    await context.close();
    console.log(JSON.stringify({summary:{passed:checks.length,failed:0},target:tag}));
  } finally { await browser.close(); }
})().catch(error => { console.error(JSON.stringify({failure_type:error.name,message:error.message})); process.exitCode=1; });
