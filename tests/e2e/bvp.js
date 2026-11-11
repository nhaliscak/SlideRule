const { chromium } = require('playwright');
// Browser test for boundary-value problems (not part of CI: needs Playwright + a running `sliderule serve --port 8775` with an empty SLIDERULE_HOME).
//   NODE_PATH=$(npm root -g) node tests/e2e/bvp.js [http://localhost:8775]
const BASE = process.argv[2] || 'http://localhost:8775';
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`); if (!ok) process.exitCode = 1; };
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1300, height: 1300 } });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));

  // ---- a library boundary-value problem (fin with a convecting tip)
  await p.goto(BASE + '/#/calc/mechanical.heat.fin_temperature_profile_convective_tip');
  await p.waitForSelector('.plot-fig', { timeout: 30000 });
  check('plot covers the interval', (await p.locator('.plot .curve').count()) === 1);
  const ode = await p.locator('.ode').innerText();
  check('shown with boundary conditions', (await p.locator('.ode .cond').count()) === 3 && ode.includes('closed form'), ode.replace(/\s+/g, ' ').slice(0, 80));
  check('result is the tip temperature', /\b\d{2,3}(\.\d+)?\s*K|°C|degC/.test(await p.locator('.results').innerText()));
  await p.screenshot({ path: 'bvp-fin.png', fullPage: true });
  await p.click('button:has-text("Symbolic solution")');
  check('steps call them boundary conditions', (await p.locator('#detail').innerText()).includes('boundary condition'));

  // ---- the nonlinear one is solved numerically
  await p.goto(BASE + '/#/calc/mechanical.heat.slab_variable_conductivity_profile');
  await p.waitForSelector('.plot-fig', { timeout: 60000 });
  check('numerical badge', (await p.locator('.ode').innerText()).includes('solved numerically'));
  await p.click('button:has-text("Symbolic solution")');
  check('steps describe multiple shooting', (await p.locator('#detail').innerText()).includes('multiple shooting'));

  // ---- the editor switches between initial values and boundary conditions
  await p.goto(BASE + '/#/mine/new');
  await p.waitForSelector('.cust-editor');
  await p.waitForSelector('button:has-text("+ Add a differential equation")', { timeout: 20000 });
  await p.click('button:has-text("+ Add a differential equation")');
  check('initial-value fields first', await p.locator('textarea[data-field="odes[0].initial"]').isVisible());
  await p.selectOption('.cust-var select >> nth=-1', 'boundary').catch(async () => { await p.locator('select:has(option[value="boundary"])').first().selectOption('boundary'); });
  await p.waitForSelector('textarea[data-field="odes[0].boundary"]');
  check('boundary fields appear, initial ones go', !(await p.locator('textarea[data-field="odes[0].initial"]').count()));
  console.log(errs.join('\n') || 'no console errors');
  if (errs.length) process.exitCode = 1;
  await b.close();
})();
