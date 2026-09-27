// Exercise the actual route modal without a server, browser or inference.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../runesmith/app/static/js/views/inference.js',import.meta.url),'utf8');
const view=source.slice(source.indexOf('async function editMillinerRoute('),source.indexOf('function instrumentRow('));
assert(view.startsWith('async function editMillinerRoute('));
function h(tag,attrs,...children) {
  if (!attrs || typeof attrs!=='object' || Array.isArray(attrs) || attrs.tag) {children.unshift(attrs);attrs={};}
  return {tag,attrs,children:children.flat(Infinity),value:attrs.value || '',append(...rows){this.children.push(...rows.flat(Infinity));}};
}
function text(node) {return node==null?'':typeof node==='string'?node:(node.children||[]).map(text).join('\n');}
function nodes(node) {return [node,...(node.children||[]).filter(n=>n&&typeof n==='object').flatMap(nodes)];}
let body,closed=0,reloaded=0;
const requests=[];
let route={name:'author',revision:'sha256:old',model:'paid:model',fallback_models:['gemini:free'],blockers:[]};
const context=vm.createContext({h,icon:()=>'',get:async path=>{requests.push(['GET',path]);return route;},
  post:async(path,data)=>{requests.push(['POST',path,data]);return {ok:true,models:['gemini3:free']};},
  modal:options=>{assert(!options.render,'modal takes body, unlike drawer');body=options.body;assert(body);return {close(){closed++;}};},
  withBusy:async(_,action)=>await action(),toast:()=>{},clear:node=>{node.children=[];return node;}});
vm.runInContext(view,context);
await context.editMillinerRoute('author',async()=>{reloaded++;});
assert.equal(requests.length,1);
assert(text(body).includes('Saving makes no inference'));
assert(text(body).includes('not a guarantee'));
let all=nodes(body);
all.find(n=>n.attrs['aria-label']==='Primary model ID').value='gemini3:free';
all.find(n=>n.attrs['aria-label']==='Fallback model IDs').value='gemini2:free\n gemini:free ';
all.find(n=>n.attrs['aria-label']==='Route change reason').value='Explicit free preference';
const save=all.find(n=>text(n).includes('Save route without a test call')&&n.tag==='button.btn.primary.mt-16');
await save.attrs.onclick({currentTarget:save});
const sent=requests.at(-1);
assert.equal(sent[1],'/api/inference/routes/author');
assert.equal(sent[2].revision,'sha256:old');
assert.equal(sent[2].model,'gemini3:free');
assert.equal(JSON.stringify(sent[2].fallback_models),JSON.stringify(['gemini2:free','gemini:free']));
assert.equal(closed,1);assert.equal(reloaded,1);
assert(!requests.some(r=>r[1].includes('/test/')||r[1].includes('/worker/')));

route={...route,blockers:['Saved request needs reconciliation']};
await context.editMillinerRoute('author',async()=>{});
assert(text(body).includes('Saved request needs reconciliation'));
assert(nodes(body).find(n=>n.tag==='button.btn.primary.mt-16').attrs.disabled);
console.log('Actual route-editor renderer: save/custody-warning cases passed; no inference.');
