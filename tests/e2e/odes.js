const { chromium } = require('playwright');
// Browser test for differential equations (not part of CI: needs Playwright + a running `sliderule serve --port 8772` with an empty SLIDERULE_HOME).
//   SLIDERULE_HOME=/tmp/sr-home sliderule serve --no-browser --port 8772 &
//   NODE_PATH=$(npm root -g) node tests/e2e/odes.js [http://localhost:8772]
const BASE = process.argv[2] || 'http://localhost:8772';
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`); if (!ok) process.exitCode = 1; };
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1300, height: 1200 } });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));

  // ---- a library calculation solved numerically: two quantities, plots, table
  await p.goto(BASE + '/#/calc/mechanical.dynamics.damped_oscillator_response');
  await p.waitForSelector('.plot-fig', { timeout: 20000 });
  check('two plots (displacement and velocity)', (await p.locator('.plot-fig').count()) === 2);
  check('plots have curves', (await p.locator('.plot .curve').count()) === 2 && ((await p.locator('.plot .curve').first().getAttribute('d')) || '').length > 200);
  check('ODE shown as written with its conditions', (await p.locator('.ode').innerText()).includes('numerically') && (await p.locator('.ode .cond').count()) === 2);
  check('table has the evaluation time row', (await p.locator('.vtable tr.eval').count()) === 1);
  await p.fill('input[aria-label="Times to tabulate"]', '0.25, 0.5, 1');
  await p.waitForFunction(() => document.querySelectorAll('.vtable tbody tr').length === 4, null, { timeout: 20000 });
  check('times to tabulate add rows', (await p.locator('.vtable tbody tr').allInnerTexts()).map(t => t.split('\t')[0]).join(',') === '0.25,0.5,1,1.5');
  await p.locator('.plot-fig').first().locator('rect').hover({ position: { x: 200, y: 60 } });
  check('hover readout', (await p.locator('.plot-readout').first().innerText()).includes('t ='));
  const [dl] = await Promise.all([p.waitForEvent('download'), p.click('button:has-text("Download CSV")')]);
  check('CSV download', dl.suggestedFilename() === 'solution.csv');
  await p.screenshot({ path: 'odes-library.png', fullPage: true });
  await p.click('button:has-text("Symbolic solution")');
  check('steps explain the differential equation', (await p.locator('#detail').innerText()).includes('governing differential equation'));

  // ---- a closed-form one: solve for the time instead
  await p.goto(BASE + '/#/calc/mechanical.thermo.newton_cooling_transient');
  await p.waitForSelector('.ode');
  check('closed-form badge', (await p.locator('.ode').innerText()).includes('solved in closed form'));
  await p.check('.row[data-key="t"] input[type=checkbox]');
  await p.uncheck('.row[data-key="T"] input[type=checkbox]');
  await p.fill('.row[data-key="T"] input.value', '40');
  await p.selectOption('.row[data-key="T"] select', '°C').catch(() => {});
  await p.waitForTimeout(1500);
  check('solving for the time works (closed form)', /min|s\b/.test(await p.locator('.results').innerText()), (await p.locator('.results').innerText()).replace(/\s+/g, ' ').slice(0, 80));

  // ---- events: projectile with drag stops at touchdown
  await p.goto(BASE + '/#/calc/mechanical.dynamics.projectile_with_drag_range');
  await p.waitForSelector('.plot .event-line', { state: 'attached', timeout: 20000 });
  check('event marker drawn on the plots', (await p.locator('.plot .event-line').count()) === 4 && (await p.locator('.plot .event-label').first().textContent()) === 'touchdown');
  check('stopped-at-event note and table marker', (await p.locator('#solution').innerText()).includes('stopped at the event') && (await p.locator('.vtable tr.eval').innerText()).includes('⏹'));
  check('flight time, range and impact velocity are results', /Flight time/.test(await p.locator('.results').innerText()) && /Range/.test(await p.locator('.results').innerText()));
  await p.screenshot({ path: 'odes-events.png', fullPage: true });

  // ---- author one in the editor
  await p.goto(BASE + '/#/mine/new');
  await p.waitForSelector('.cust-editor');
  await p.fill('input[data-field="name"]', 'Decay');
  await p.locator('#view-mine').getByRole('button', { name: 'Chemical', exact: true }).click();
  const vars = p.locator('.cust-var');
  const set = async (i, key, label, unit, ex) => {
    await vars.nth(i).locator(`input[data-field="variables[${i}].key"]`).fill(key);
    await vars.nth(i).locator(`input[data-field="variables[${i}].label"]`).fill(label);
    await vars.nth(i).locator(`input[data-field="variables[${i}].unit"]`).fill(unit);
    if (ex) await vars.nth(i).locator('input[placeholder="e.g. 250 kN"]').fill(ex);
  };
  await set(0, 'N', 'Amount at time t', 'mol', '');
  await set(1, 'N0', 'Initial amount', 'mol', '2 mol');
  await set(2, 'k', 'Decay constant', '1/s', '0.1 1/s');
  await p.locator('#view-mine button:text-is("+ Add variable")').click();
  await set(3, 't', 'Time', 's', '10 s');
  await p.locator('#view-mine button:has-text("Add a differential equation")').click();
  await p.fill('textarea[data-field="odes[0].equations"]', 'diff(N, t) = -k*N');
  await p.fill('textarea[data-field="odes[0].initial"]', 'N = N0');
  await p.waitForFunction(() => /solved in closed form/.test(document.querySelector('.cust-check')?.innerText || ''), null, { timeout: 30000 });
  check('editor previews the ODE and its solution kind', true, (await p.locator('.cust-check').innerText()).replace(/\s+/g, ' ').slice(0, 140));
  await p.fill('textarea[data-field="odes[0].initial"]', '');
  await p.waitForFunction(() => /missing initial value/.test(document.querySelector('.cust-check')?.innerText || ''), null, { timeout: 30000 });
  check('missing initial value explained', true);
  await p.fill('textarea[data-field="odes[0].initial"]', 'N = N0');
  await p.waitForSelector('.cust-check .ok');
  await p.click('button:has-text("Save and open")');
  await p.waitForSelector('.plot-fig', { timeout: 20000 });
  check('saved custom ODE opens with a plot', (await p.locator('#detail').innerText()).includes('Decay'));
  console.log(errs.join('\n') || 'no console errors');
  if (errs.length) process.exitCode = 1;
  await b.close();
})();
