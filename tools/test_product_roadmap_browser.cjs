const { chromium } = require('playwright-core');
const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname, '../docs/product-roadmap');
const screenshots=process.env.PH_ROADMAP_SCREENSHOTS;
if(screenshots) fs.mkdirSync(screenshots,{recursive:true});
const screenshot=async(page,name)=>{ if(screenshots) await page.screenshot({path:path.join(screenshots,name)}); };
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--host-resolver-rules=MAP * ~NOTFOUND']});
 try {
 const page=await browser.newPage({viewport:{width:1440,height:1100}});let errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 let url=pathToFileURL(root+'/index.html').href;
 await page.goto(url+'?lang=en');
 await page.waitForSelector('.feature-card'); assert.equal(await page.locator('.feature-card').count(),26);
 await page.locator('#area-nav button[data-area=operations]').click();
 assert.equal(await page.locator('.feature-card').count(),1);
 assert.match(await page.locator('#installation-and-recovery').innerText(),/Installation and recovery/);
 await page.locator('#clear-filters').click();
 await page.locator('#literal-search details').evaluate(e=>e.open=true);
 await page.locator('[data-language=zh]').click();
 assert.equal(await page.locator('html').getAttribute('lang'),'zh-CN');
 assert.equal(await page.locator('#literal-search details').getAttribute('open'),'');
 assert.match(await page.locator('#literal-search').innerText(),/结构化照片搜索/);
 await page.locator('#stage-filter').selectOption('source_ready');
 assert.equal(await page.locator('.feature-card').count(),3);
 await page.locator('#search-input').fill('cloud');assert.equal(await page.locator('.feature-card').count(),1);
 await page.locator('[data-language=en]').click();assert.equal(await page.locator('#search-input').inputValue(),'cloud');assert.equal(await page.locator('.feature-card').count(),1);
 await page.locator('#clear-filters').click();
 await screenshot(page,'ph-roadmap-desktop-en.png');
 await page.locator('[data-language=zh]').click();await screenshot(page,'ph-roadmap-desktop-zh.png');
 for (const width of [320,390]) {
  await page.setViewportSize({width,height:900});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow ${width}`);
  await screenshot(page,`ph-roadmap-phone-${width}-zh.png`);
 }
 await page.setViewportSize({width:1280,height:960});await page.evaluate(()=>document.documentElement.style.fontSize='32px');
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'200% text overflow');
 await screenshot(page,'ph-roadmap-large-zh.png');
 await page.evaluate(()=>document.documentElement.style.fontSize='');await page.goto(url+'?lang=en#automatic-intake');
 assert.equal(await page.locator('#automatic-intake details').getAttribute('open'),'');
 assert.equal(await page.locator('html').getAttribute('lang'),'en');
 await page.locator('#search-input').fill('no-such-feature-qx');assert.equal(await page.locator('.feature-card').count(),0);assert.ok(await page.locator('#empty-state').isVisible());
 await page.locator('#empty-state button').click();assert.equal(await page.locator('.feature-card').count(),26);
 await page.goto(url+'?lang=zh');await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.className),'skip-link');
 assert.deepEqual(errors,[]);
 console.log('PASS bilingual content, URL override, filter/search/detail preservation, empty state, deep link, keyboard, 320/390/1440 and 200% layout');
 } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1});
