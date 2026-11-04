// Run with Node and Playwright available on NODE_PATH; uses local Edge, no server/DB.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const records = Array.from({ length: 603 }, (_, i) => ({
      lead_id: String(i), business_name: 'Synthetic ' + i,
      country: 'DO', business_category: 'Testing', status: 'qualified', version: 1,
    }));
    const requests = [];
    let failNextLeads = false;
    let releaseSlow;
    const slowResponse = new Promise(resolve => { releaseSlow = resolve; });
    await page.route('http://dashboard.test/**', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html',
        body: fs.readFileSync(path.join(__dirname, '../app/static/index.html'), 'utf8') });
      let body;
      if (url.pathname === '/api/options') body = {
        countries: ['DO'], business_categories: ['Testing'], owners: [], statuses: ['new', 'qualified'],
      };
      else if (url.pathname === '/api/summary') body = {
        total: 603, new_today: 0, follow_up: 0, converted: 0, countries: 1, categories: 1,
        no_contact: 603, top_countries: [], top_categories: [],
      };
      else if (/^\/api\/leads\/\d+$/.test(url.pathname)) {
        body = records[Number(url.pathname.split('/').at(-1))];
        if (route.request().method() === 'PATCH') Object.assign(body, route.request().postDataJSON());
      } else if (url.pathname === '/api/leads') {
        requests.push(url.searchParams);
        if (failNextLeads) {
          failNextLeads = false;
          return route.fulfill({ status: 503, json: { detail: 'Synthetic unavailable' } });
        }
        const offset = Number(url.searchParams.get('offset') || 0);
        const limit = Number(url.searchParams.get('limit') || 500);
        const items = records.slice(offset, offset + limit);
        body = url.searchParams.get('paginated') === 'true'
          ? { items, total: records.length, offset, limit, has_more: offset + items.length < records.length }
          : items;
        if (url.searchParams.get('q') === 'slow') {
          await slowResponse;
          body = { items: [{ ...records[0], business_name: 'Stale response' }], total: 999,
            offset, limit, has_more: true };
        }
      } else throw Error('Unexpected request: ' + url);
      await route.fulfill({ json: body });
    });
    await page.goto('http://dashboard.test/');
    await page.waitForFunction(() => document.querySelector('#statusFilter').options.length === 3);
    await page.selectOption('#statusFilter', 'qualified');
    await page.evaluate(() => refresh());
    assert.equal(await page.inputValue('#statusFilter'), 'qualified', 'Refresh must preserve status');
    assert.equal(await page.locator('#leadPagination').isVisible(), false);
    await page.evaluate(() => showView('table'));
    await page.waitForFunction(() => document.querySelector('#rows').children.length === 100);
    assert.match(await page.locator('#pageSummary').innerText(), /100 loaded.*603 matching/);
    assert.equal(await page.locator('#previousPage').isDisabled(), true);
    for (let i = 1; i <= 6; i++) {
      await page.click('#nextPage');
      await page.waitForFunction(offset => leadOffset === offset && !leadsLoading, i * 100);
    }
    assert.equal(await page.locator('#rows tr').count(), 3);
    assert.match(await page.locator('#rows').innerText(), /Synthetic 602/);
    assert.equal(await page.locator('#nextPage').isDisabled(), true);
    for (const view of ['kanban', 'mywork', 'country', 'business']) {
      await page.evaluate(view => showView(view), view);
      assert.equal(await page.locator('#leadPagination').isVisible(), true);
      assert.match(await page.locator('#pageSummary').innerText(), /603 matching/);
    }
    await page.selectOption('#country', 'DO');
    await page.selectOption('#category', 'Testing');
    await page.waitForFunction(() => leadOffset === 0 && !leadsLoading);
    await page.click('#nextPage');
    await page.waitForFunction(() => leadOffset === 100 && !leadsLoading);
    const last = requests.at(-1);
    assert.equal(last.get('country'), 'DO');
    assert.equal(last.get('business_category'), 'Testing');
    assert.equal(last.get('status'), 'qualified');
    assert.equal(last.get('limit'), '100');
    assert.equal(last.get('offset'), '100');
    assert.equal(last.get('paginated'), 'true');
    await page.evaluate(() => openLead('100'));
    await page.locator('[name="next_action"]').fill('Synthetic follow up');
    await page.evaluate(() => saveLead());
    assert.equal(await page.inputValue('#statusFilter'), 'qualified', 'Save-triggered refresh must preserve status');
    assert.equal(requests.at(-1).get('status'), 'qualified');
    for (const view of ['country', 'business']) {
      assert.match(await page.locator('#v-' + view + ' .section-head').innerText(), /current page/);
    }
    const slowRequest = page.waitForRequest(request => new URL(request.url()).searchParams.get('q') === 'slow');
    await page.evaluate(() => { document.querySelector('#q').value = 'slow'; window.slowLoad = loadLeads(); });
    await slowRequest;
    await page.evaluate(() => { document.querySelector('#q').value = ''; return loadLeads(); });
    releaseSlow();
    await page.evaluate(() => window.slowLoad);
    assert.match(await page.locator('#pageSummary').innerText(), /603 matching/);
    assert.doesNotMatch(await page.locator('#rows').innerText(), /Stale response/);
    failNextLeads = true;
    await page.evaluate(() => refresh());
    assert.match(await page.locator('#pageSummary').innerText(), /Could not load matching leads/);
    assert.doesNotMatch(await page.locator('#pageSummary').innerText(), /0 matching/);
    assert.doesNotMatch(await page.locator('#toast').innerText(), /Workspace refreshed/);
    assert.equal(await page.locator('#nextPage').isDisabled(), true);
    await page.evaluate(() => refresh());
    assert.match(await page.locator('#pageSummary').innerText(), /603 matching/);
    assert.doesNotMatch(await page.locator('#pageSummary').innerText(), /Could not load/);
    assert.match(await page.locator('#toast').innerText(), /Workspace refreshed/);
    assert.deepEqual(errors, []);
    console.log('DASHBOARD_PAGINATION=PASS status refresh/save, 603 records, bounded requests, shared views, filters, stale responses');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
