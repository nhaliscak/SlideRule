const { chromium } = require('playwright');
// Browser check of derivative/integral equations (not part of CI): needs Playwright + `sliderule serve --port 8768` (with an empty SLIDERULE_HOME).
//   NODE_PATH=$(npm root -g) node tests/e2e/calculus.js [http://localhost:8768]
const BASE = process.argv[2] || 'http://localhost:8768';
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1300,height:1100}});const errs=[];
p.on('console',m=>{if(m.type()==='error')errs.push(m.text())});p.on('pageerror',e=>errs.push('PE '+e.message));
await p.goto(BASE+'/#/calc/mechanical.work_energy.variable_force_work');
await p.waitForSelector('.eq .evaluated');await p.waitForTimeout(800);
console.log('as written + evaluated shown:', await p.locator('.eq').first().innerText().then(t=>t.replace(/\s+/g,' ').slice(0,120)));
console.log('katex errors on page:', await p.locator('.katex-error').count());
await p.click('button:has-text("Symbolic solution")');await p.waitForTimeout(500);
console.log('steps contain as-written note:', (await p.locator('#detail').innerText()).includes('as written'));
await p.screenshot({path:'calculus-calc.png'});
// editor with calculus
await p.goto(BASE+'/#/mine/new');await p.waitForSelector('.cust-editor');
await p.fill('input[data-field="name"]','Work of a ramp force');
await p.locator('#view-mine').getByRole('button',{name:'Mechanical',exact:true}).click();
const vars=p.locator('.cust-var');
for (const [i,k,l,u,ex] of [[0,'W','Work','J',''],[1,'F0','Peak force','N','10 kN'],[2,'d','Distance','m','3 m']]){
 const v=vars.nth(i);await v.locator(`input[data-field="variables[${i}].key"]`).fill(k);await v.locator(`input[data-field="variables[${i}].label"]`).fill(l);await v.locator(`input[data-field="variables[${i}].unit"]`).fill(u);if(ex)await v.locator('input[placeholder="e.g. 250 kN"]').fill(ex);}
await p.fill('input[data-field="equations[0].text"]','W = integrate(F0*x/d, (x, 0, d))');
await p.waitForSelector('.cust-check .ok');await p.waitForTimeout(500);
console.log('editor preview:', await p.locator('.cust-check').innerText().then(t=>t.replace(/\s+/g,' ').slice(0,200)));
await p.screenshot({path:'calculus-editor.png'});
await p.fill('input[data-field="equations[0].text"]','W = integrate(F0*x/d, x)');
await p.waitForFunction(()=>document.querySelector('.cust-check')?.innerText.includes('definite'));
console.log('indefinite refused with explanation: true');
console.log(errs.join('\n')||'no console errors');await b.close();})();
