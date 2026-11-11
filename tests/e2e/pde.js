const { chromium } = require('playwright');
// Browser test for partial differential equations (not part of CI: needs Playwright + a running `sliderule serve --port 8776` with an empty SLIDERULE_HOME).
//   NODE_PATH=$(npm root -g) node tests/e2e/pde.js [http://localhost:8776]
const BASE = process.argv[2] || 'http://localhost:8776';
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`); if (!ok) process.exitCode = 1; };
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1300, height: 1500 } });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));

  await p.goto(BASE + '/#/calc/mechanical.heat.slab_transient_convective_cooling');
  await p.waitForSelector('.plot-fig', { timeout: 60000 });
  check('two figures: profile and history', (await p.locator('.plot-fig').count()) === 2);
  check('profile has one curve per snapshot time', (await p.locator('.plot-fig').first().locator('.curve.snap').count()) >= 5);
  check('legend names the times', (await p.locator('.plot-legend').first().innerText()).includes('t = 0'));
  check('the equation is shown with boundary and initial conditions', (await p.locator('.ode .cond').count()) >= 4);
  const notes = await p.locator('.panel .hint').allInnerTexts();
  check('discretisation error estimate is shown', notes.some((n) => n.includes('estimated discretisation error')), notes[0] || '');
  await p.locator('.plot-fig').first().locator('rect').hover({ position: { x: 200, y: 60 } });
  check('hover readout lists the curves', (await p.locator('.plot-readout').first().innerText()).includes('t = 0'));
  await p.fill('input[aria-label="Times to tabulate"]', '10, 20');
  await p.waitForFunction(() => document.querySelectorAll('.vtable tbody tr').length === 3, null, { timeout: 60000 });
  check('times to tabulate add rows', true);
  const [dl] = await Promise.all([p.waitForEvent('download'), p.click('button:has-text("Download CSV")')]);
  check('CSV download', dl.suggestedFilename() === 'solution.csv');
  await p.screenshot({ path: 'pde-slab.png', fullPage: true });
  await p.click('button:has-text("Symbolic solution")');
  check('steps describe the partial differential equation', (await p.locator('#detail').innerText()).includes('governing differential equation'));

  await p.goto(BASE + '/#/mine/new');
  await p.waitForSelector('.cust-editor');
  await p.click('button:has-text("+ Add a differential equation")');
  await p.locator('select:has(option[value="pde"])').first().selectOption('pde');
  await p.waitForSelector('textarea[data-field="odes[0].boundary"]');
  check('PDE fields appear', (await p.locator('input[data-field="odes[0].time"]').count()) === 1);
  console.log(errs.join('\n') || 'no console errors');
  if (errs.length) process.exitCode = 1;
  await b.close();
})();
