const { chromium } = require('playwright');
// NOTE: written after the same flow was driven by hand in the built-in browser pane; Playwright was not installed when this was written, so the script itself has not been run.
// Browser test for the property-data picker (not part of CI: needs Playwright and a running `sliderule serve --port 8770`).
//   sliderule serve --no-browser --port 8770 &
//   NODE_PATH=$(npm root -g) node tests/e2e/data_picker.js [http://localhost:8770]
const BASE = process.argv[2] || 'http://localhost:8770';
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`); if (!ok) process.exitCode = 1; };
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1300, height: 900 } });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  await p.goto(BASE + '/#/calc/mechanical.fluid.pipe_system_losses_swamee_jain');
  await p.waitForSelector('.row[data-key="rho"] .data-btn');
  check('density and viscosity inputs offer property data', (await p.locator('.data-btn').count()) >= 2);
  check('a computed (unknown) result does not', await p.locator('.row[data-key="dp"] .data-btn').isHidden());

  await p.click('.row[data-key="rho"] .data-btn');
  await p.waitForSelector('dialog.data-dialog[open]');
  await p.selectOption('dialog.data-dialog select[aria-label="material or fluid"]', 'fluids-water-air/water-liquid');
  await p.fill('dialog.data-dialog input[aria-label="temperature"]', '40');
  await p.waitForFunction(() => document.querySelector('.data-preview .big')?.innerText.startsWith('992.2'));
  check('water at 40 degC previews 992.2 kg/m3 with its basis and "not for design"', (await p.locator('.data-preview').innerText()).includes('not for design'));
  await p.fill('dialog.data-dialog input[aria-label="temperature"]', '150');
  await p.waitForSelector('.data-preview.bad');
  check('outside the stored range there is no value', await p.locator('dialog.data-dialog button:text-is("Use this value")').isDisabled());
  await p.fill('dialog.data-dialog input[aria-label="temperature"]', '40');
  await p.waitForFunction(() => document.querySelector('.data-preview .big')?.innerText.startsWith('992.2'));
  await p.click('dialog.data-dialog button:text-is("Use this value")');
  check('the value is filled in', (await p.inputValue('.row[data-key="rho"] input.value')) === '992.216');
  check('its source is shown beside it', (await p.locator('.row[data-key="rho"] .data-prov').innerText()).includes('fluids-water-air v0.1.0'));
  await p.fill('.row[data-key="rho"] input.value', '990');
  check('editing by hand is flagged', (await p.locator('.row[data-key="rho"] .data-prov').innerText()).includes('edited by hand'));
  await p.click('.row[data-key="rho"] .data-prov button');
  check('the source note can be dropped', await p.locator('.row[data-key="rho"] .data-prov').isHidden());
  check('no console errors', errs.length === 0, errs.join(' | '));
  await b.close();
})();
