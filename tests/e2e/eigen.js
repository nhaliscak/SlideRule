const { chromium } = require('playwright');
// Browser test for unknown parameters in boundary-value problems (not part of CI: needs Playwright + a running `sliderule serve --port 8778` with an empty SLIDERULE_HOME).
//   NODE_PATH=$(npm root -g) node tests/e2e/eigen.js [http://localhost:8778]
const BASE = process.argv[2] || 'http://localhost:8778';
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`); if (!ok) process.exitCode = 1; };
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1300, height: 1400 } });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  await p.goto(BASE + '/#/calc/civil.structural.cable_horizontal_tension_from_length');
  await p.waitForSelector('.plot-fig', { timeout: 60000 });
  await p.waitForFunction(() => /H\s*=\s*7\.2/.test(document.querySelector('.results')?.innerText.replace(/\s+/g, ' ') || ''), null, { timeout: 60000 });
  check('horizontal tension found as an output', true, (await p.locator('.results').innerText()).replace(/\s+/g, ' ').slice(0, 90));
  check('shown as an unknown found with the solution', (await p.locator('.ode').innerText()).includes('found together with the solution'));
  await p.goto(BASE + '/#/calc/civil.column.buckling_load_tapered_stiffness');
  await p.waitForFunction(() => /P\s*=\s*64/.test(document.querySelector('.results')?.innerText.replace(/\s+/g, ' ') || ''), null, { timeout: 60000 });
  check('buckling load found (mode shape plotted)', (await p.locator('.plot-fig').count()) >= 1);
  await p.screenshot({ path: 'eigen.png', fullPage: true });
  await p.goto(BASE + '/#/mine/new');
  await p.waitForSelector('.cust-editor');
  await p.click('button:has-text("+ Add a differential equation")');
  await p.locator('select:has(option[value="boundary"])').first().selectOption('boundary');
  await p.waitForSelector('input[data-field="odes[0].unknowns"]');
  check('unknown-parameters field in the boundary-value editor', true);
  console.log(errs.join('\n') || 'no console errors');
  if (errs.length) process.exitCode = 1;
  await b.close();
})();
