'use strict';
/* Actual Web component with generated reader/job data; no provider or live API. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const repo=path.resolve(__dirname,'../../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-wording-review-'));
fs.mkdirSync(artifacts,{recursive:true});
let browser;
(async()=>{
  browser=await chromium.launch({headless:true,args:['--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND']});
  const context=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'block'}),errors=[],external=[];
  await context.route('**/*',async route=>{
    if(route.request().url()!=='https://photohouse.test/'){external.push(route.request().url());await route.abort();return;}
    await route.fulfill({contentType:'text/html',body:'<!doctype html><html lang="zh"><meta name="viewport" content="width=device-width"><body><main id="host" style="max-width:100%;padding:12px"></main></body></html>'});
  });
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.goto('https://photohouse.test/');
  await page.addStyleTag({content:fs.readFileSync(path.join(repo,'server/backend/app/ui/access/styles.css'),'utf8')});
  await page.addScriptTag({content:fs.readFileSync(path.join(repo,'server/backend/app/ui/access/memory-community.js'),'utf8')});
  await page.evaluate(async()=>{
    const scope={account:'11111111-1111-4111-8111-111111111111',library:'synthetic-library',membership_revision:'1',language:'zh',locked:false};
    const chapters=[
      {id:'chapter-1',title:'相同章节',narration:'我们种下了向日葵。',asset_ids:['1'],evidence_ids:['family-1']},
      {id:'chapter-2',title:'变化章节',narration:'后来一起浇水。',asset_ids:['2'],evidence_ids:[]},
      {id:'chapter-3',title:'尚未加载正文',narration:null,asset_ids:['3'],evidence_ids:[]},
    ];
    const target={type:'story',id:'22222222-2222-4222-8222-222222222222',revision:'7',title:'当前故事',theme:'everyday',language:'zh',can_edit:true,selection_revision:'a'.repeat(64),chapters,
      items:[{id:'1',evidence:[{id:'family-1',source:'family',text:'这是独立的来源原话。'}]}]};
    const result={version:1,needs_review:true,title:'建议标题 <b>仍是文字</b>',questions:['请问家人：花开在什么时候？'],chapters:[
      {id:'chapter-1',narration:chapters[0].narration,source_ids:['family-1']},
      {id:'chapter-2',narration:'每天清晨，我们轮流照看幼苗。',source_ids:[]},
      {id:'chapter-3',narration:'这段建议仍需核对。',source_ids:[]},
    ]};
    const calls=[],adoptions=[],original=JSON.stringify(target);let baseRevision='7',generation=0,audioStops=0;
    window.addEventListener('photohouse-memory-audio-start',()=>audioStops++);
    const ui=window.PhotoHouseMemoryCommunity({scope,onProposal:value=>adoptions.push(value),request:async(path,options={})=>{
      calls.push({path,method:options.method||'GET'});
      if(path.endsWith('/capabilities'))return {version:1,enabled:true,contributions_enabled:false,generation_enabled:true};
      if(path.includes('/conversations?'))return {version:1,items:[]};
      if(path.includes('/jobs')&&options.method==='POST')return {version:1,id:`33333333-3333-4333-8333-${String(++generation).padStart(12,'0')}`,kind:'narrative',state:'ready',base_revision:baseRevision,result};
      throw new Error('Unexpected synthetic request');
    }});
    window.fixture={scope,target,result,calls,adoptions,original,ui,setBase:value=>baseRevision=value,audioStops:()=>audioStops};
    await ui.attach(document.querySelector('#host'),target);
  });
  const generate=async()=>{
    await page.getByRole('tab',{name:/整理建议|Draft suggestions/,exact:true}).click();
    await page.locator('.memory-community-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
    await page.locator('.memory-proposal-wording-toggle').waitFor();
  };
  await generate();
  const chapters=page.locator('.memory-community-proposal-chapter'),toggle=page.locator('.memory-proposal-wording-toggle');
  assert.equal(await page.locator('.memory-proposal-wording-summary').textContent(),'章节正文：1 章不同 · 1 章相同 · 1 章暂不可对照');
  assert.equal(await toggle.getAttribute('aria-pressed'),'false');
  assert(await chapters.nth(0).getByText('我们种下了向日葵。',{exact:true}).first().isVisible());
  assert.equal(await page.locator('.memory-community-proposal b').count(),0,'proposal markup stays literal');
  const requestsBefore=await page.evaluate(()=>window.fixture.calls.length);
  await toggle.focus();await page.keyboard.press('Enter');
  assert.equal(await toggle.getAttribute('aria-pressed'),'true');
  assert.equal(await page.locator('.memory-proposal-review-label:visible').count(),3,'all chapter review labels remain visible while prose is collapsed');
  assert.equal(await chapters.nth(0).getByText('我们种下了向日葵。',{exact:true}).first().isVisible(),false);
  assert(await chapters.nth(1).getByText('每天清晨，我们轮流照看幼苗。',{exact:true}).isVisible());
  assert(await chapters.nth(2).getByText('这段建议仍需核对。',{exact:true}).isVisible());
  assert(await chapters.nth(2).getByText('当前正文暂不可对照',{exact:true}).isVisible());
  await chapters.nth(0).locator('.memory-proposal-sources summary').click();
  assert(await chapters.nth(0).getByText('这是独立的来源原话。',{exact:true}).isVisible(),'matching wording never hides source review');
  assert(await page.getByText('请问家人：花开在什么时候？',{exact:true}).isVisible());
  assert(await page.getByRole('button',{name:'将建议带入编辑',exact:true}).isVisible());
  assert.equal(await page.evaluate(()=>window.fixture.calls.length),requestsBefore,'filtering does not request or save anything');
  assert.equal(await page.evaluate(()=>window.fixture.adoptions.length),0);
  assert.equal(await page.evaluate(()=>JSON.stringify(window.fixture.target)===window.fixture.original),true);
  assert.equal(await page.evaluate(()=>window.fixture.audioStops()),1,'a local view change stops prior read-aloud without starting it');
  await toggle.click();assert(await chapters.nth(0).getByText('我们种下了向日葵。',{exact:true}).first().isVisible());
  console.log('PASS Mixed chapter review is local, reversible, literal and keeps references, questions and adoption separate');
  for(const language of ['zh','en']){
    await page.evaluate(async language=>{window.fixture.scope.language=language;await window.fixture.ui.translate();},language);
    await toggle.waitFor();assert.equal(await toggle.getAttribute('aria-pressed'),'false','a fresh render starts with all wording');
    await page.evaluate(()=>document.documentElement.style.fontSize='24px');
    await toggle.click();await toggle.scrollIntoViewIfNeeded();
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert((await toggle.boundingBox()).height>=48);
    await page.locator('.memory-proposal-wording-review').screenshot({path:path.join(artifacts,`proposal-wording-${language}-150.png`)});
  }
  console.log('PASS English and Chinese review controls fit 390 px at 150 percent text and remain keyboard reachable');
  await toggle.evaluate(node=>window.retiredToggle=node);
  await page.evaluate(async()=>{window.fixture.ui.clear();await window.fixture.ui.attach(document.querySelector('#host'),window.fixture.target);});
  await generate();await page.evaluate(()=>window.retiredToggle.click());
  assert.equal(await toggle.getAttribute('aria-pressed'),'false','detached previous controls cannot change a new review');
  await page.evaluate(()=>{window.fixture.ui.clear();window.fixture.setBase('6');});
  await page.evaluate(()=>window.fixture.ui.attach(document.querySelector('#host'),window.fixture.target));await generate();
  assert.match(await page.locator('.memory-proposal-wording-summary').textContent(),/0 different.*0 matching.*3 unavailable/);
  assert.equal(await page.locator('.memory-proposal-comparison').count(),0,'stale jobs cannot show current text as a matched comparison');
  await toggle.click();assert.equal(await chapters.locator('p:not([hidden])').filter({hasText:'Current wording unavailable'}).count(),3);
  console.log('PASS Replaced readers reject stale controls and revision mismatches never count as matching wording');
  await page.evaluate(async()=>{
    const f=window.fixture;f.ui.clear();f.setBase('7');
    f.target.chapters=f.target.chapters.slice(0,2);f.target.chapters[1].narration='';
    f.result.chapters=f.target.chapters.map(chapter=>({id:chapter.id,narration:chapter.narration,source_ids:['family-1']}));
    await f.ui.attach(document.querySelector('#host'),f.target);
  });await generate();
  assert.match(await page.locator('.memory-proposal-wording-summary').textContent(),/0 different.*2 matching.*0 unavailable/);
  assert.equal(await page.locator('.memory-proposal-wording-text').evaluateAll(nodes=>nodes.filter(node=>!node.hidden).length),2,'even blank matching text participates in exact comparison');
  await toggle.click();assert.equal(await page.locator('.memory-proposal-wording-text').evaluateAll(nodes=>nodes.filter(node=>!node.hidden).length),0);
  assert.equal(await chapters.locator('.memory-proposal-sources:visible').count(),2,'all-matching review keeps references available');
  assert(await page.getByText('请问家人：花开在什么时候？',{exact:true}).isVisible());
  console.log('PASS All-matching and blank wording collapse only prose while retaining title, references and questions');
  await page.evaluate(async()=>{
    const f=window.fixture;f.ui.clear();f.target.chapters[1].id='chapter-1';
    f.result.chapters[1].id='chapter-1';await f.ui.attach(document.querySelector('#host'),f.target);
  });await generate();
  assert.match(await page.locator('.memory-proposal-wording-summary').textContent(),/0 different.*0 matching.*2 unavailable/);
  await toggle.click();assert.equal(await page.locator('.memory-proposal-wording-text').evaluateAll(nodes=>nodes.filter(node=>!node.hidden).length),2,'ambiguous IDs never hide proposed wording');
  assert.equal(await page.locator('.memory-proposal-comparison').count(),0,'ambiguous IDs never pick an arbitrary current chapter');
  console.log('PASS Duplicate chapter identities remain unavailable and visible');
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  console.log('ARTIFACTS '+artifacts);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();});
