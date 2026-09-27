// Exercise the real Studio drawer without a server, browser or model call.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../runesmith/app/static/js/views/work.js',import.meta.url),'utf8');
const view=source.slice(source.indexOf('async function showRevisionContext('),source.indexOf('function drawDrafts('));
assert(view.startsWith('async function showRevisionContext('));
function h(tag,attrs,...children) {
  if(!attrs || typeof attrs!=='object' || Array.isArray(attrs) || attrs.tag){children.unshift(attrs);attrs={};}
  return {tag,attrs,children:children.flat(Infinity),value:attrs.value||'',append(...rows){this.children.push(...rows.flat(Infinity));}};
}
function text(n){return n==null?'':typeof n==='string'?n:(n.children||[]).map(text).join('\n');}
function nodes(n){return [n,...(n.children||[]).filter(x=>x&&typeof x==='object').flatMap(nodes)];}
let body,closed=0,reloaded=0;
let data={version:'frozen-v1',blockers:[],settings:null,max_units:12,code_budget_chars:24000,
  scope:'Saving grants no calls, retries, checks or apply.',units:[
    {path:'app.py',unit:'*',label:'Complete file',chars:28000},
    {path:'app.py',unit:'target@4',label:'target',chars:80}],
  preview:{broad_prompt_bytes:90000,focused_prompt_bytes:null,prompt:null}};
const requests=[];
const context=vm.createContext({h,icon:()=>'',get:async path=>{requests.push(['GET',path]);return data;},
  post:async(path,payload)=>{requests.push(['POST',path,payload]);return {};},
  drawer:({render})=>{body=h('body');render(body,()=>{closed++;});},
  clear:n=>{n.children=[];return n;},withBusy:async(_,fn)=>await fn(),toast:()=>{}});
vm.runInContext(view,context);
await context.showRevisionContext('d123',async()=>{reloaded++;});
assert(text(body).includes('not a complete dependency graph'));
assert(text(body).includes('not tokens'));
let all=nodes(body);
assert(all.find(n=>n.attrs.type==='checkbox').attrs.disabled);
const checkbox=all.find(n=>n.attrs.type==='checkbox'&&!n.attrs.disabled);
checkbox.attrs.onchange({target:{checked:true}});
all.find(n=>n.attrs['aria-label']==='Revision context reason').value='Small explicit correction';
const save=all.find(n=>n.tag==='button.btn.primary');
await save.attrs.onclick({currentTarget:save});
const sent=requests.find(r=>r[0]==='POST');
assert.equal(sent[1],'/api/drafts/d123/revision-context');
assert.equal(sent[2].version,'frozen-v1');
assert.equal(JSON.stringify(sent[2].selections),JSON.stringify([{path:'app.py',unit:'target@4'}]));
assert.equal(sent[2].enabled,true);
assert.equal(closed,1);assert.equal(reloaded,1);
assert(!requests.some(r=>r[1].includes('/worker/')||r[1].includes('/apply')));
data={...data,blockers:['Reconcile pending author'],settings:{enabled:true,selections:[],reason:'existing'},
  feedback:{enabled:true,included:[{id:'latest',author:'external-trainer',target:{type:'draft',id:'d123'}}],
    omitted:[{id:'older',reason:'whole note exceeds remaining context budget'}],used_chars:200,budget_chars:3000},
  preview:{broad_prompt_bytes:90000,focused_prompt_bytes:21000,prompt:'Exact retained candidate view'}};
await context.showRevisionContext('d123',async()=>{});
assert(nodes(body).find(n=>n.tag==='button.btn.primary').attrs.disabled);
assert(text(body).includes('Reconcile pending author'));
assert(text(body).includes('Included latest · external-trainer'));
assert(text(body).includes('Omitted older · whole note exceeds remaining context budget'));
assert(nodes(body).find(n=>n.attrs['aria-label']==='Focused author packet preview').attrs.readOnly);
console.log('Actual revision-context drawer: selection/CAS/preview/blocker cases passed; no inference.');
