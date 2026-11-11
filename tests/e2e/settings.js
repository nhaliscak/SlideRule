const { chromium } = require('playwright');
// Browser test for the time-limit setting (not part of CI: needs Playwright + a freshly started `sliderule serve --port 8770`
// with an empty SLIDERULE_HOME, because the last check relies on SymPy's cold start making one integral genuinely slow).
//   SLIDERULE_HOME=/tmp/sr-home sliderule serve --no-browser --port 8770 &
//   NODE_PATH=$(npm root -g) node tests/e2e/settings.js [http://localhost:8770] [/tmp/sr-home]
const BASE = process.argv[2] || 'http://localhost:8770';
const HOME = process.argv[3] || '';
const fs = require('fs');
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`); if (!ok) process.exitCode = 1; };
const api = async (p, path, body) => (await p.evaluate(async ([path, body]) => (await fetch(path, body ? { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {})).json(), [path, body]));
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1300, height: 900 } });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  await p.goto(BASE + '/');
  await p.waitForSelector('#settings-btn');
  check('no warning badge by default', await p.locator('#limit-badge').isHidden());

  await p.click('#settings-btn');
  await p.waitForSelector('dialog[open]');
  check('limit on, 10 s by default', (await p.isChecked('#limit-on')) && (await p.inputValue('#limit-secs')) === '10');
  check('no warning while the limit is on', await p.locator('.warn-box').isHidden());
  await p.uncheck('#limit-on');
  check('warning appears when switching off', await p.locator('.warn-box').isVisible() && (await p.locator('.warn-box').innerText()).includes('never finishes'));
  check('seconds field disabled and Save blocked until acknowledged', (await p.locator('#limit-secs').isDisabled()) && (await p.locator('dialog button:text-is("Save")').isDisabled()));
  await p.screenshot({ path: 'settings-warning.png' });
  await p.check('#limit-ack');
  check('Save enabled after acknowledging', await p.locator('dialog button:text-is("Save")').isEnabled());
  await p.click('dialog button:text-is("Save")');
  await p.waitForSelector('#limit-badge:not([hidden])');
  check('badge shows that there is no limit', true);
  check('engine agrees', (await api(p, '/api/settings')).timeout_enabled === false);
  if (HOME) check('persisted to settings.json', JSON.parse(fs.readFileSync(HOME + '/settings.json', 'utf8')).timeout_enabled === false);

  await p.reload();
  await p.waitForSelector('#limit-badge:not([hidden])');
  check('still off after reload', true);

  await p.click('#limit-badge');
  await p.waitForSelector('dialog[open]');
  check('dialog shows it is off', !(await p.isChecked('#limit-on')));
  await p.check('#limit-on');
  await p.fill('#limit-secs', '0');
  check('invalid seconds block Save', await p.locator('dialog button:text-is("Save")').isDisabled());
  await p.fill('#limit-secs', '1');
  await p.click('dialog button:text-is("Save")');
  await p.waitForSelector('#limit-badge', { state: 'hidden' });
  const s = await api(p, '/api/settings');
  check('limit back on at 1 s', s.timeout_enabled && s.timeout_seconds === 1);

  // a slow integral is stopped by the setting and the editor says so
  await p.goto(BASE + '/#/mine/new');
  await p.waitForSelector('.cust-editor');
  await p.fill('input[data-field="name"]', 'slow');
  await p.locator('#view-mine').getByRole('button', { name: 'Mechanical', exact: true }).click();
  const vars = p.locator('.cust-var');
  for (const [i, k] of [[0, 'Q'], [1, 'd']]) {
    await vars.nth(i).locator(`input[data-field="variables[${i}].key"]`).fill(k);
    await vars.nth(i).locator(`input[data-field="variables[${i}].label"]`).fill(k);
  }
  await vars.nth(2).locator('button:has-text("Remove")').click();
  await p.fill('input[data-field="equations[0].text"]', 'Q = integrate(exp(-x**2)*sin(x)/(1 + x**4), (x, 0, d))');
  await p.waitForFunction(() => /longer than 1 s/.test(document.querySelector('.cust-check')?.innerText || ''), null, { timeout: 30000 });
  check('slow integral stopped at the configured limit', true, (await p.locator('.cust-check').innerText()).replace(/\s+/g, ' ').slice(0, 150));
  await api(p, '/api/settings', { timeout_seconds: 10 });
  console.log(errs.join('\n') || 'no console errors');
  if (errs.length) process.exitCode = 1;
  await b.close();
})();
