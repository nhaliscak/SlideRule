const { chromium } = require('playwright');
// Browser test for numerical inversion (not part of CI: needs Playwright + a running `sliderule serve --port 8774` with an empty SLIDERULE_HOME).
//   NODE_PATH=$(npm root -g) node tests/e2e/inversion.js [http://localhost:8774]
const BASE = process.argv[2] || 'http://localhost:8774';
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`); if (!ok) process.exitCode = 1; };
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1300, height: 1100 } });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  await p.goto(BASE + '/');
  await p.waitForSelector('.list .card');
  // a numerically solved cooling equation, created through the API
  const doc = { id: 'custom.cooling_num', name: 'Cooling (numerical)', disciplines: ['mechanical'], outputs: ['T'],
    variables: [{ key: 'T', label: 'Temperature at time t', unit: 'K' }, { key: 'T0', label: 'Initial temperature', unit: 'K', example: '363.15 K' }, { key: 'Ta', label: 'Ambient', unit: 'K', example: '293.15 K' },
      { key: 'k', label: 'Rate constant', unit: '1/s', example: '0.01 1/s' }, { key: 't', label: 'Time', unit: 's', example: '120 s' }],
    odes: [{ independent: 't', method: 'numeric', equations: ['diff(T, t) = -k*(T - Ta)'], initial: ['T = T0'] }] };
  const saved = await p.evaluate(async (doc) => (await fetch('/api/custom', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ calculation: doc }) })).status, doc);
  check('custom numerical ODE saved', saved === 200);
  await p.goto(BASE + '/#/calc/custom.cooling_num');
  await p.waitForSelector('.row[data-key="k"]');
  await p.waitForSelector('.results');
  check('forward result first', (await p.locator('.results').innerText()).includes('314.2'));
  // solve for k from a known temperature instead
  await p.uncheck('.row[data-key="T"] input[type=checkbox]').catch(() => {});
  await p.check('.row[data-key="k"] input[type=checkbox]');
  await p.uncheck('.row[data-key="T"] input[type=checkbox]');
  await p.fill('.row[data-key="T"] input.value', '314.2336');
  await p.waitForFunction(() => /Rate constant/.test(document.querySelector('.results')?.innerText || '') && /0\.01/.test(document.querySelector('.results')?.innerText || ''), null, { timeout: 30000 });
  check('rate constant found by root-finding', true, (await p.locator('.results').innerText()).replace(/\s+/g, ' ').slice(0, 70));
  check('explained in the diagnostics', (await p.locator('.diag').innerText()).includes('found numerically'));
  check('search range is offered for the unknown', await p.locator('.row[data-key="k"] details.search-range').isVisible());
  await p.locator('.row[data-key="k"] details.search-range summary').click();
  await p.fill('input[aria-label="Rate constant search from"]', '0.1');
  await p.fill('input[aria-label="Rate constant search to"]', '5');
  await p.waitForFunction(() => /no value of k|Cannot calculate/.test(document.querySelector('#solution')?.innerText || ''), null, { timeout: 30000 });
  check('a range without the answer is reported clearly', (await p.locator('#solution').innerText()).includes('no sign change'));
  await p.fill('input[aria-label="Rate constant search from"]', '0.001');
  await p.fill('input[aria-label="Rate constant search to"]', '1');
  await p.waitForFunction(() => /0\.01/.test(document.querySelector('.results')?.innerText || ''), null, { timeout: 30000 });
  check('a range that contains it works again', true);
  await p.screenshot({ path: 'inversion.png', fullPage: true });
  console.log(errs.join('\n') || 'no console errors');
  if (errs.length) process.exitCode = 1;
  await b.close();
})();
