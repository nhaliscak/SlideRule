const { chromium } = require('playwright');
// Browser test for steady 2-D partial differential equations (not part of CI: needs Playwright + a running `sliderule serve --port 8777` with an empty SLIDERULE_HOME).
//   NODE_PATH=$(npm root -g) node tests/e2e/pde2d.js [http://localhost:8777]
const BASE = process.argv[2] || 'http://localhost:8777';
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`); if (!ok) process.exitCode = 1; };
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1300, height: 1500 } });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  await p.goto(BASE + '/#/calc/electrical.rf.potential_in_rectangular_trough');
  await p.waitForSelector('svg.heat', { timeout: 60000 });
  check('heat map drawn with cells', (await p.locator('svg.heat rect.cell').count()) > 1000);
  check('three figures: field and two profiles', (await p.locator('.plot-fig').count()) === 3);
  await p.locator('svg.heat').hover({ position: { x: 300, y: 100 } });
  check('hover readout gives the potential', /Vp = /.test(await p.locator('.plot-readout').first().innerText()));
  const [dl] = await Promise.all([p.waitForEvent('download'), p.locator('button:has-text("Download CSV")').first().click()]);
  check('CSV download', dl.suggestedFilename() === 'solution.csv');
  await p.screenshot({ path: 'pde2d.png', fullPage: true });
  await p.goto(BASE + '/#/mine/new');
  await p.waitForSelector('.cust-editor');
  await p.click('button:has-text("+ Add a differential equation")');
  await p.locator('select:has(option[value="steady2d"])').first().selectOption('steady2d');
  await p.waitForSelector('textarea[data-field="odes[0].boundary"]');
  check('2-D fields appear', (await p.locator('input[data-field="odes[0].second"]').count()) === 1);
  console.log(errs.join('\n') || 'no console errors');
  if (errs.length) process.exitCode = 1;
  await b.close();
})();
