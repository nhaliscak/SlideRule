const { chromium } = require('playwright');
// Browser test for the System Design editor (not part of CI: needs Playwright + a running `sliderule serve`).
//   NODE_PATH=$(npm root -g) node tests/e2e/system_design.js /tmp/shots [http://localhost:8765]
const out = process.argv[2] || '.';
const BASE = process.argv[3] || 'http://localhost:8765';
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1500, height: 900 } });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('dialog', d => d.accept());
  await p.goto(BASE + '/#/design');
  await p.waitForSelector('.canvas');
  await p.waitForSelector('#listpane .card');
  console.log('list items:', await p.locator('#listpane .card').count());
  const canvas = p.locator('.canvas');
  const cb = await canvas.boundingBox();

  async function addBlock(query, x, y) {
    await p.fill('#sidebar input[type=search]', query);
    await p.waitForTimeout(500);
    await p.locator('#listpane .card').first().dragTo(canvas, { targetPosition: { x, y } });
    await p.waitForTimeout(400);
  }
  await addBlock('ISA standard atmosphere', 150, 60);
  await addBlock('Lift, drag and dynamic', 560, 60);
  console.log('nodes after drag/drop:', await p.locator('.node').count());

  const center = async (sel) => { const bb = await p.locator(sel).first().boundingBox(); return { x: bb.x + bb.width / 2, y: bb.y + bb.height / 2 }; };
  async function wire(fromSel, toSel) {
    const a = await center(fromSel), c = await center(toSel);
    await p.mouse.move(a.x, a.y); await p.mouse.down(); await p.mouse.move((a.x + c.x) / 2, (a.y + c.y) / 2, { steps: 5 }); await p.mouse.move(c.x, c.y, { steps: 5 }); await p.mouse.up();
    await p.waitForTimeout(300);
  }
  const wires = () => p.locator('svg.wires g.wire').count();
  console.log('wires at start:', await wires());

  // incompatible: pressure output -> area input
  await wire('.port[data-key="p"][data-role="output"]', '.port[data-key="S"][data-role="input"]');
  console.log('after incompatible attempt, wires =', await wires(), '| toast:', (await p.locator('.badge[role=status]').allTextContents()).join(' | ').slice(0, 160));
  // wrong direction: input -> input
  await wire('.port[data-key="h"][data-role="input"]', '.port[data-key="S"][data-role="input"]');
  console.log('input->input, wires =', await wires(), '| toast:', (await p.locator('.badge[role=status]').allTextContents()).pop());
  // compatible: density -> density
  await wire('.port[data-key="rho"][data-role="output"]', '.port[data-key="rho"][data-role="input"]');
  console.log('after compatible wire, wires =', await wires());
  // second wire into the same input is refused
  await wire('.port[data-key="rho"][data-role="output"]', '.port[data-key="rho"][data-role="input"]');
  console.log('duplicate into same input, wires =', await wires());
  await p.waitForTimeout(900);
  await p.screenshot({ path: out + '/d1.png' });

  // click the lift block: inspector appears; flip CD to a constant, then CL to an output (invalid combination)
  await p.locator('.node', { hasText: 'Lift, drag' }).locator('.nhead').click();
  await p.waitForSelector('.inspector .roles');
  console.log('inspector rows:', await p.locator('.inspector .rrow').count());
  const row = (key) => p.locator('.inspector .rrow', { has: p.locator(`.sym`) }).filter({ hasText: key });
  await p.locator('.inspector .rrow').filter({ hasText: 'Drag coefficient' }).locator('button', { hasText: 'Const' }).click();
  await p.waitForTimeout(700);
  console.log('CD constant -> node shows constants group:', await p.locator('.node', { hasText: 'Lift, drag' }).locator('.crow').count());
  await p.locator('.inspector .rrow').filter({ hasText: 'Reference area' }).locator('button', { hasText: 'Output' }).click();
  await p.waitForTimeout(800);
  console.log('S -> output, node status:', await p.locator('.node', { hasText: 'Lift, drag' }).getAttribute('class'), '| inspector errors:', (await p.locator('.inspector ul.diag li.error').allTextContents()).join(' || ').slice(0, 220));
  await p.screenshot({ path: out + '/d2.png' });
  // undo that: S back to input
  await p.locator('.inspector .rrow').filter({ hasText: 'Reference area' }).locator('button', { hasText: 'Input' }).click();
  await p.waitForTimeout(900);
  console.log('restored, status:', await p.locator('.node', { hasText: 'Lift, drag' }).getAttribute('class'));
  console.log('result badge on lift output:', (await p.locator('.node', { hasText: 'Lift, drag' }).locator('.prow.output .val').allTextContents()).join(', '));

  // delete the wire by selecting it and pressing Delete
  const wb = await p.locator('svg.wires g.wire path.hit').first().boundingBox();
  await p.mouse.click(wb.x + wb.width / 2, wb.y + wb.height / 2);
  await p.keyboard.press('Delete');
  await p.waitForTimeout(300);
  console.log('after deleting wire:', await wires());
  // export: LaTeX download
  await p.selectOption('select[aria-label="Export format"]', 'latex');
  const [dl] = await Promise.all([p.waitForEvent('download'), p.locator('button', { hasText: /^Export$/ }).click()]);
  const fs = require('fs'); const path = await dl.path();
  const tex = fs.readFileSync(path, 'utf8');
  console.log('export file:', dl.suggestedFilename(), tex.includes('\\documentclass') ? 'has documentclass' : 'MISSING documentclass');
  console.log(errs.join('\n') || 'no console errors');
  await b.close();
})();
