const { chromium } = require('playwright');
// Browser test for "My equations" (not part of CI: needs Playwright + a running `sliderule serve`, started with SLIDERULE_HOME pointing at an empty folder).
//   SLIDERULE_HOME=/tmp/sr-home sliderule serve --no-browser &
//   NODE_PATH=$(npm root -g) node tests/e2e/custom_equations.js /tmp/shots http://localhost:8765 /tmp/sr-home
const out = process.argv[2] || '.';
const BASE = process.argv[3] || 'http://localhost:8765';
const HOME = process.argv[4] || '';
const fs = require('fs');
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`); if (!ok) process.exitCode = 1; };
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1400, height: 1000 }, acceptDownloads: true });
  const p = await ctx.newPage();
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('dialog', d => d.accept());
  await p.goto(BASE + '/#/mine');
  await p.waitForSelector('.cust-list');
  check('empty state', (await p.locator('.cust-list .empty').count()) === 1);

  // ---- create an equation through the form
  await p.click('text=New equation');
  await p.waitForSelector('.cust-editor');
  await p.fill('input[data-field="name"]', 'Spring force');
  await p.fill('#view-mine textarea >> nth=0', 'Hooke\'s law for a linear spring');
  await p.locator('#view-mine').getByRole('button', { name: 'Mechanical', exact: true }).click();
  const vars = p.locator('.cust-var');
  const setVar = async (i, key, label, unit, example) => {
    const v = vars.nth(i);
    await v.locator(`input[data-field="variables[${i}].key"]`).fill(key);
    await v.locator(`input[data-field="variables[${i}].label"]`).fill(label);
    await v.locator(`input[data-field="variables[${i}].unit"]`).fill(unit);
    if (example) await v.locator('input[placeholder="e.g. 250 kN"]').fill(example);
  };
  await setVar(0, 'F', 'Force', 'N', '');
  await setVar(1, 'k', 'Stiffness', 'N/m', '2 kN/m');
  await setVar(2, 'x', 'Extension', 'm', '5 cm');
  await p.fill('input[data-field="equations[0].text"]', 'F = k*x**2');
  await p.waitForFunction(() => document.querySelector('.cust-check')?.innerText.includes('not dimensionally homogeneous'));
  check('dimension error shown', (await p.locator('.cust-check').innerText()).includes('not dimensionally homogeneous'));
  check('save disabled while invalid', await p.locator('button:has-text("Save and open")').isDisabled());
  await p.fill('input[data-field="equations[0].text"]', "F = __import__('os')");
  await p.waitForFunction(() => document.querySelector('.cust-check')?.innerText.includes('unknown function'));
  check('unsafe expression refused', true);
  await p.fill('input[data-field="equations[0].text"]', 'F = k*x');
  await p.waitForSelector('.cust-check .ok');
  check('valid + preview', (await p.locator('.cust-check .katex').count()) >= 1 && (await p.locator('.cust-check').innerText()).includes('Example gives'));
  await p.screenshot({ path: out + '/mine-editor.png' });
  await p.click('button:has-text("Save and open")');
  await p.waitForSelector('.badge.custom');
  await p.waitForSelector('.result, .results, .out, [class*=result]');
  await p.waitForTimeout(800);
  const body = await p.locator('#detail').innerText();
  check('opens in calculator with custom badge + banner', body.includes('Spring force') && body.includes('User-defined'));
  check('worked example solved (F = 100 N)', /100\s*N/.test(body), body.match(/F\s*=\s*[^\n]*/)?.[0] || '');
  await p.screenshot({ path: out + '/mine-calc.png' });
  check('tab shows count', (await p.locator('.tabs button[data-view="mine"]').innerText()).includes('(1)'));
  if (HOME) check('saved as a file', fs.existsSync(HOME + '/calculations/spring_force.json'));

  // ---- search, filter
  await p.goto(BASE + '/#/');
  await p.check('.only-mine input');
  await p.waitForTimeout(500);
  check('"Only my equations" filter', (await p.locator('.list .card').count()) === 1);
  await p.uncheck('.only-mine input');

  // ---- edit
  await p.goto(BASE + '/#/mine');
  await p.click('.cust-card >> text=Edit');
  await p.waitForSelector('.cust-editor');
  check('editor loads existing values', (await p.inputValue('input[data-field="name"]')) === 'Spring force');
  await p.fill('input[data-field="name"]', 'Spring force (linear)');
  await p.waitForSelector('.cust-check .ok');
  await p.click('button:has-text("Save"):not(:has-text("open"))');
  await p.waitForSelector('.cust-card');
  check('rename persisted', (await p.locator('.cust-card h3').innerText()).includes('linear'));

  // ---- export / delete / import
  await p.goto(BASE + '/#/mine');
  await p.waitForSelector('.cust-card');
  const [dl] = await Promise.all([p.waitForEvent('download'), p.click('.cust-card >> text=Export file')]);
  const file = out + '/' + dl.suggestedFilename();
  await dl.saveAs(file);
  const doc = JSON.parse(fs.readFileSync(file, 'utf8'));
  check('export file format', doc.format === 'sliderule-calculations' && doc.calculations[0].id === 'custom.spring_force');
  await p.click('.cust-card >> text=Delete');
  await p.waitForSelector('.cust-list .empty');
  check('deleted', true);
  if (HOME) check('file removed', !fs.existsSync(HOME + '/calculations/spring_force.json'));
  await p.setInputFiles('#view-mine input[type=file]', file);
  await p.waitForSelector('.cust-card');
  check('re-imported', (await p.locator('.report').innerText()).includes('added'));
  await p.screenshot({ path: out + '/mine-list.png' });

  // ---- a malicious file is rejected without side effects
  const evil = out + '/evil.json';
  fs.writeFileSync(evil, JSON.stringify({ ...doc.calculations[0], id: 'custom.evil', equations: [{ text: "F = k*x + __import__('os').system('touch /tmp/pwned-by-e2e')" }] }));
  await p.setInputFiles('#view-mine input[type=file]', evil);
  await p.waitForSelector('.report li.bad');
  check('unsafe file rejected', (await p.locator('.report').innerText()).includes('plain function') && !fs.existsSync('/tmp/pwned-by-e2e'));

  // ---- System Design: use it, save graph with embedded equation, delete, load
  await p.goto(BASE + '/#/design');
  await p.waitForSelector('#listpane .card');
  await p.fill('#sidebar input[type=search]', 'Spring force');
  await p.waitForTimeout(500);
  check('list shows it with badge', (await p.locator('#listpane .card .badge.custom').count()) >= 1);
  await p.locator('#listpane .card').filter({ has: p.locator('.badge.custom') }).first().click();
  await p.waitForTimeout(600);
  check('block added', (await p.locator('.node').count()) === 1);
  const [gdl] = await Promise.all([p.waitForEvent('download'), p.click('#design button:text-is("Save")')]);
  const gfile = out + '/graph.json';
  await gdl.saveAs(gfile);
  const g = JSON.parse(fs.readFileSync(gfile, 'utf8'));
  check('graph embeds the custom equation', g.custom_calculations?.[0]?.id === 'custom.spring_force');
  await p.goto(BASE + '/#/mine');
  await p.click('.cust-card >> text=Delete');
  await p.waitForSelector('.cust-list .empty');
  await p.goto(BASE + '/#/design');
  await p.waitForSelector('.canvas');
  await p.click('#design button:text-is("Clear")');
  await p.setInputFiles('#design input[type=file]', gfile);
  await p.waitForTimeout(1200);
  check('loading the graph restores the equation and the block', (await p.locator('.node').count()) === 1);
  await p.goto(BASE + '/#/mine');
  await p.waitForSelector('.cust-card');
  check('equation back in My equations', (await p.locator('.cust-card').count()) === 1);
  console.log(errs.join('\n') || 'no console errors');
  if (errs.length) process.exitCode = 1;
  await b.close();
})();
