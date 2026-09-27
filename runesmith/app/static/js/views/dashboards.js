// Read-only general/project dashboards. Controls change views, not execution.
import {h, icon, get, post, clear, bus, debounce, withBusy, toast, drawer, confirmDialog} from '../core.js';
import {gatewayUsage} from '../gateway-usage.js';
import {measurementReadiness} from '../measurement-readiness.js';

const LABELS={progress:'Build & goals',modes:'Modes & operations',measurements:'Measurements & connections',activity:'Work history',inference:'Models & estimated usage'};
const text=v=>v===null||v===undefined?'unknown':String(v);

export default async function render(root,ctx){
  root.classList.add('dashboard-page');let selected='general',data,closed=false;
  const head=h('div.page-head',h('div',h('h2','Dashboards'),h('p','Overall progress and a dashboard for each tracked project. Views read saved evidence; they never start work or turn a missing measurement into a success.')));
  const tabs=h('div.row.wrap.mb-8'),body=h('div');
  const refresh=h('button.btn',{onclick:e=>withBusy(e.currentTarget,load)},icon('refresh'),'Refresh receipts');
  const add=h('button.btn.primary',{onclick:()=>addProject()},icon('plus'),'Add project dashboard');
  head.append(h('div.actions',refresh,add));root.append(head,tabs,body);
  async function mutate(payload,revision=data.revision){await post('/api/dashboards',{revision,...payload});await load();}
  function addProject(){const revision=data.revision;drawer({title:'Add project dashboard',sub:'Read-only view of an existing local folder',render(box,close){
    const name=h('input.input',{'aria-label':'Dashboard name'}),folder=h('input.input.mono',{'aria-label':'Project folder',placeholder:'Absolute local path'}),home=h('input.input.mono',{'aria-label':'Runesmith home',placeholder:'Optional: defaults to <project>/.runesmith'});
    box.append(h('p.small','This only registers a view. No project initialization, model call, scheduler, source change or new permission. Missing homes appear unavailable. Use a custom home for isolated instances.'),
      ...[['Dashboard name',name],['Project folder',folder],['Runesmith home',home]].map(([label,node])=>h('label.col.mt-8',h('span',label),node)),
      h('button.btn.primary.mt-16',{onclick:e=>withBusy(e.currentTarget,async()=>{await mutate({action:'add',project:{name:name.value,root:folder.value,home:home.value}},revision);close();toast('Dashboard added. No worker started.');})},'Add read-only dashboard'));
  }});}
  function customize(p){const revision=data.revision;drawer({title:`Panels — ${p.name}`,sub:'Show or hide information without changing the project',render(box,close){
    const chosen=new Set(p.panels);
    for(const key of data.panels)box.append(h('label.row.mt-8',h('input',{type:'checkbox',checked:chosen.has(key),'aria-label':LABELS[key],onchange:e=>e.target.checked?chosen.add(key):chosen.delete(key)}),LABELS[key]));
    box.append(h('button.btn.primary.mt-16',{onclick:e=>withBusy(e.currentTarget,async()=>{await mutate({action:'panels',project_id:p.id,panels:[...chosen]},revision);close();})},'Save dashboard panels'));
  }});}
  function projectSummary(p){
    const card=h('section.card',h('div.card-head',h('h3',p.name),h('span.badge',p.available?'Saved receipts':'Unavailable')),
      h('p.tiny.mono',p.root),h('p.tiny.muted',`Observed ${p.observed_at}`));
    if(!p.available)card.append(h('p.small.warn',p.detail));
    else card.append(h('p.small',p.progress.milestone_total?`${p.progress.milestones.done||0}/${p.progress.milestone_total} milestones recorded done`:'No recorded milestones'),
      h('p.small',`${p.measurements.length} measurement definitions · ${p.activity.length} recent retained jobs`),
      h('p.tiny.muted',`Last build verification: ${text(p.build.verification)} — not necessarily current source.`));
    if(p.available&&p.gateway_accounting){
      const s=p.gateway_accounting.summary,c=p.gateway_accounting.coverage;
      card.append(h('p.small',`Gateway estimate subtotal: ${s.estimated_usd==null?'unknown':'$'+Number(s.estimated_usd).toFixed(6)} · ${s.costed_requests}/${s.requests} retained requests covered`),
        h('p.tiny.muted',`${s.unresolved} unresolved/conflicting · ${c.invalid} invalid receipts · ${c.omitted} outside the window. Not total spend or remaining credit.`));
    }
    if(p.errors.length)card.append(h('p.small.warn',`${p.errors.length} unreadable evidence item(s). Inspect the project dashboard.`));
    card.append(h('button.btn.sm',{onclick:()=>{selected=p.id;draw();}},'Open project dashboard'));return card;
  }
  function draw(){
    clear(tabs).append(...[{id:'general',name:'General'},...data.projects].map(p=>h('button',{class:'btn '+(p.id===selected?'primary':''),'aria-pressed':p.id===selected,onclick:()=>{selected=p.id;draw();}},p.name)));
    clear(body).append(h('p.small.muted',data.scope));
    if(selected==='general'){body.append(h('div.grid.two',...data.projects.map(projectSummary)));return;}
    const p=data.projects.find(p=>p.id===selected);if(!p){selected='general';draw();return;}
    body.append(h('div.card-head',h('h3',p.name),h('button.btn.sm',{onclick:()=>customize(p)},'Customize panels'),
      p.id==='current'?h('button.btn.sm',{onclick:()=>ctx.navigate('mission')},'Modes & measurements'):h('button.btn.sm',{onclick:e=>withBusy(e.currentTarget,async()=>{
        if(!await confirmDialog({title:'Remove this dashboard?',text:'Only this saved view is removed. Project files, evidence and any running worker are untouched.',confirm:'Remove view'}))return;
        await mutate({action:'remove',project_id:p.id});
      })},'Remove dashboard')),
      h('p.tiny.mono',`${p.root} · home ${p.home}`));
    if(!p.available){body.append(h('p.callout.warn',p.detail));return;}
    body.append(h('p.tiny.muted',p.scope));
    for(const error of p.errors)body.append(h('p.callout.warn',error));
    if(p.recorded_inflight)body.append(h('p.callout.warn',`Recorded in-flight job ${p.recorded_inflight.kind} since ${p.recorded_inflight.started}. This file does not establish that a worker is still running.`));
    const grid=h('div.grid.two');body.append(grid);
    for(const key of p.panels){
      const card=h('section.card',h('h3',LABELS[key]));grid.append(card);
      if(key==='progress')card.append(h('p.small',`${p.progress.milestones.done||0}/${p.progress.milestone_total} milestones recorded done · ${p.progress.goals.active||0} active goals`),
        h('p.tiny',`Plan author: ${text(p.progress.plan_author)} · plan time: ${text(p.progress.plan_at)}`),
        h('p.small',`Last retained build: ${text(p.build.verification)} · applied: ${text(p.build.applied)}`),h('p.tiny.muted',p.progress.scope),h('p.tiny.muted',p.build.scope));
      if(key==='modes'){
        card.append(h('p.tiny.muted','Operations currently means local report intake. Optimize currently proposes hypotheses; neither label proves production activity or improvement.'));
        if(!p.modes_configured)card.append(h('p.small','No explicit mode configuration recorded; legacy behavior may apply.'));
        for(const m of p.modes)card.append(h('div.item',h('div.body',h('b',`${m.name} · ${m.enabled===null?'unknown':m.enabled?'on':'off'}`),h('p.small',m.summary||'No completed mode receipt.'),h('p.tiny',`Recorded: ${text(m.utc)}`))));
      }
      if(key==='measurements'){
        if(!p.measurements.length)card.append(h('p.small','No measurement definitions yet. Add goals and report sources under Modes & measurements in that project.'));
        for(const m of p.measurements)card.append(h('div.item',h('div.body',h('b',m.name||m.id),
          h('p.small',`${m.status} · ${text(m.value)} ${m.unit||''} · ${m.connector}`),
          h('p.tiny',`Goal: ${m.goal||'not linked'} · enabled: ${text(m.enabled)} · receipt ${text(m.receipt)}`),
          h('p.tiny',`Measured ${text(m.measured_at)} · data through ${text(m.latest_data_at)}`),
          h('p.tiny',`Recorded threshold (historical): ${text(m.threshold_met)} · source: ${text(m.source_kind)}`),
          m.current_definition===false?h('p.callout.warn','Stale definition: this receipt used different measurement settings.'):null,
          measurementReadiness(m.assessment),m.assessment?null:h('p.tiny.muted',m.freshness))));
      }
      if(key==='activity'){
        if(!p.activity.length)card.append(h('p.small','No retained Studio job history. Absence is not a success.'));
        for(const j of p.activity)card.append(h('div.item',h('div.body',h('b',`${j.kind} · ${j.result}`),h('p.small',j.summary),h('p.tiny',`${text(j.finished)} · ${text(j.seconds)}s · ${text(j.id)}`))));
      }
      if(key==='inference'){
        card.append(gatewayUsage(p.gateway_accounting),
          h('h4.mt-16','Legacy host callback counters'),
          h('p.tiny.muted','These counters may predate reconciliation and omit late recoveries. They are not gateway attempts or validated spend. Do not add their estimates to the gateway subtotal.'));
        if(!p.inference.length)card.append(h('p.small','No instrument usage receipt.'));
        for(const i of p.inference)card.append(h('div.item',h('div.body',h('b',i.instrument),h('p.small',`${text(i.model)} · ${text(i.calls)} host callbacks · ${text(i.errors)} errors`),h('p.tiny',`${i.estimated_usd==null?'Legacy estimate unknown':'$'+i.estimated_usd+' legacy estimate (not reconciled)'} · cost fields on ${text(i.costed_calls)}/${text(i.calls)} calls · last ${text(i.last_utc)}`))));
      }
    }
    if(!p.panels.length)body.append(h('p.small','All panels are hidden. Use Customize panels to add them back.'));
  }
  async function load(){const fresh=await get('/api/dashboards');if(closed)return;data=fresh;draw();}
  await load();
  const offs=['dashboards','job','mission','plan','work','goals','inference'].map(event=>bus.on(event,debounce(()=>load().catch(e=>toast(e.message,'warn')),500)));
  return()=>{closed=true;root.classList.remove('dashboard-page');offs.forEach(off=>off());};
}
