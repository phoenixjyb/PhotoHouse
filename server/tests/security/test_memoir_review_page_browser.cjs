'use strict';
/* Private operator review fixtures only: fake provider, no API, DB or model. */
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const root = path.resolve(__dirname, '../../..');
const artifacts = process.env.PH_BROWSER_ARTIFACTS || fs.mkdtempSync(path.join(os.tmpdir(), 'photohouse-review-page-'));
fs.mkdirSync(artifacts, {recursive: true, mode: 0o700});
const fixtures = path.join(artifacts, 'fixtures');
execFileSync(process.env.PH_BROWSER_PYTHON || 'python3', ['-c',
  'import sys;sys.path.insert(0,sys.argv[1]);from test_memoir_review_page import write_browser_fixtures;write_browser_fixtures(sys.argv[2])',
  __dirname, fixtures], {cwd: root, stdio: 'pipe'});
let browser;
(async () => {
  browser = await chromium.launch({headless: true, args: ['--disable-background-networking', '--host-resolver-rules=MAP * ~NOTFOUND']});
  const context = await browser.newContext({viewport: {width: 1365, height: 1000}, serviceWorkers: 'block'});
  const unexpected = [], errors = [];
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    const name = url.pathname.slice(1);
    if (url.origin !== 'https://photohouse.test' || !/^synthetic-[a-z-]+\.html$/.test(name) || !fs.existsSync(path.join(fixtures, name))) {
      unexpected.push(route.request().url());
      return route.abort();
    }
    return route.fulfill({contentType: 'text/html; charset=utf-8', body: fs.readFileSync(path.join(fixtures, name))});
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  let groups = 0;
  for (const name of ['synthetic-coherence', 'synthetic-conflict', 'synthetic-provenance', 'synthetic-title-abstention', 'synthetic-title-family']) {
    await page.goto(`https://photohouse.test/${name}.html`);
    await page.getByRole('heading', {name: '故事与来源审阅'}).waitFor();
    assert.equal(await page.locator('script,img,iframe,form').count(), 0);
    assert.equal(await page.locator('#review').getByText('当前源码评审要点 · 全部未评审', {exact: true}).count(), 1);
    for (const width of [1365, 390]) {
      await page.setViewportSize({width, height: 1000});
      await page.evaluate(size => document.documentElement.style.fontSize = size, width === 390 ? '150%' : '100%');
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${name}: no horizontal overflow at ${width}`);
      const columns = await page.locator('.layout').evaluate(el => getComputedStyle(el).gridTemplateColumns.trim().split(/\s+/).length);
      assert.equal(columns, width === 390 ? 1 : 2, 'CSP permits the exact stylesheet');
      if (name === 'synthetic-coherence' && width === 390) {
        assert(await page.locator('#wording .chapter').first().evaluate(el => el.getBoundingClientRect().top < innerHeight), 'wording remains reachable above the fold at large text');
      }
      if (name === 'synthetic-coherence' || (name === 'synthetic-conflict' && width === 390)) {
        await page.screenshot({path: path.join(artifacts, `${name}-${width}.png`), fullPage: false});
      }
    }
    if (name === 'synthetic-title-family') {
      assert(await page.locator('#wording').innerText().then(text => text.includes('<img src=')), 'model markup remains literal');
    } else if (name === 'synthetic-provenance') {
      assert(await page.getByText('最近对话：不是已确认来源', {exact: true}).isVisible());
    } else if (name === 'synthetic-title-abstention') {
      assert(await page.getByText('没有标题建议。空来源时应保留这一结果，不补造标题。', {exact: true}).isVisible());
    }
    const source = page.locator('#wording a[href^="#source-"]').first();
    if (await source.count()) {
      await source.focus();
      await page.keyboard.press('Enter');
      const id = await source.getAttribute('href');
      assert.equal(new URL(page.url()).hash, id);
      assert(await page.locator(id).evaluate(el => {const r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight;}));
    }
    groups++;
  }
  assert.deepEqual(unexpected, []);
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(artifacts, 'result.json'), JSON.stringify({groups, synthetic_only: true, model_run: false, external_requests: 0}));
  console.log(JSON.stringify({groups, synthetic_only: true, model_run: false, external_requests: 0}));
})().catch(error => {console.error(error); process.exitCode = 1;})
  .finally(async () => {if (browser) await browser.close();});
