import test from 'node:test';
import assert from 'node:assert/strict';
import {buildCatalog,matchesSession,sessionHref,sessionSummary} from '../public/catalog.mjs';

function card(id,model,od='Fast',hz=180,conditions={},valid=1,mean=3){
  return {id,monitor:{model,overdrive:od,refresh_hz:hz},conditions,
    measured_at:'2026-11-23',simulation:false,summary:{valid,total:valid+1,
      g2g_ms:{mean,min:mean,max:mean},overshoot_pct:{mean:2,min:2,max:2}}};
}

test('alias conhecido agrupa configurações e mantém variantes de modelo distintas',()=>{
  const models=buildCatalog([
    card('1','LG UltraGear 24GS60F-B'),card('2','  lg 24gs60f – b ','Faster'),
    card('3','24GS60F-B','Fast',60),card('4','LG 24GS60F-W'),
    card('5','AOC LM522'),card('6','AOC LM522A'),
  ]);
  assert.equal(models.length,4);
  const lg=models.find(model=>model.key==='lg-24gs60f-b');
  assert.equal(lg.sessions.length,3);
  assert.equal(lg.sessions.filter(s=>matchesSession(s,{query:'LG 24GS60F-B',hz:'180',overdrive:'fast'})).length,1);
  assert.equal(lg.sessions.filter(s=>matchesSession(s,{hz:'60'})).length,1);
});

test('agrupa partes da mesma revisão com média ponderada e conserva a URL individual',()=>{
  const part={campaign_id:'camp',campaign_step:'step',campaign_session:'sid',campaign_dataset:'version',report_parts:2};
  const a=card('1','AOC LM522','Único',60,{...part,report_part:1},2,2);
  const b=card('2','AOC LM522','Único',60,{...part,report_part:2},6,6);
  const c=card('3','AOC LM522','Único',60,{...part,campaign_dataset:'other',report_part:1});
  const [model]=buildCatalog([a,b,c]);
  assert.equal(model.sessions.length,2);
  const complete=model.sessions.find(s=>s.complete);
  assert.equal(sessionHref(complete),'?relatorio=1&completo=1');
  assert.equal(sessionSummary(complete).g2g_ms.mean,5);
  assert.equal(sessionHref(model.sessions.find(s=>!s.complete)),'?relatorio=3');
});
