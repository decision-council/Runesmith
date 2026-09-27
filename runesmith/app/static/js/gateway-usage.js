// Shared read-only projection renderer for Thinking power and project dashboards.
import {h, humanize} from './core.js';

const money=v=>v==null?'unknown':'$'+Number(v).toFixed(6);
const count=v=>v==null?'unknown':Number(v).toLocaleString('en-US');
function tokens(u,field){
  return u[field]==null?`${count(u['observed_'+field])} observed; total unknown`:count(u[field]);
}

export function gatewayUsage(report){
  if(!report)return h('p.small.muted','Gateway accounting unavailable. No zero-spend claim.');
  const s=report.summary,c=report.coverage;
  const box=h('div.gateway-usage',h('h4','Gateway usage & cost coverage'),
    h('p.small',report.scope),
    h('div.row.wrap',h('span.badge',`${s.requests} deduplicated requests/tickets`),
      h('span.badge',`${s.terminal} terminal`),h('span.badge',`${s.unresolved} unresolved/conflicting`)),
    h('p',h('b',`Estimated subtotal: ${money(s.estimated_usd)}`),
      ` · ${s.costed_requests}/${s.requests} requests have included reported estimates.`),
    h('p.small',`${count(s.attempt_reconciled_requests)} attempt-reconciled · ${count(s.aggregate_only_requests)} aggregate-only (no cross-attempt check).`),
    h('p.small',`${s.token_complete_requests}/${s.requests} requests have complete reported token counts.`),
    h('p.tiny.muted',`Receipt window: ${c.scanned} scanned, ${c.valid} valid, ${c.duplicates} duplicate copies, ${c.invalid} invalid/unreadable, ${c.omitted} outside the window.`),
    h('p.callout.warn',report.caution));
  if(!s.requests)box.append(h('p.small','No valid retained gateway request in this window. This is not evidence of zero spend.'));
  if(s.unresolved)box.append(h('p.small','Unresolved tickets remain unknown. Retrieve the original ticket in Work & proposals; do not resubmit it.'));
  const details=h('details',h('summary','Inspect request accounting'));
  for(const r of report.requests){
    const u=r.usage;
    details.append(h('div.card.mt-8',
      h('h4',{style:{overflowWrap:'anywhere'}},r.instrument),
      h('p.small.mono',{style:{overflowWrap:'anywhere'}},r.job_ids?.length>1?'Conflicting tickets: '+r.job_ids.join(' · '):r.job_id||'No bound ticket'),
      h('p.small',`${humanize(r.state)}${r.outcome?' · '+humanize(r.outcome):''}`),
      h('p.small',`${count(u.attempts)} recorded gateway attempts · ${count(u.token_complete_attempts)} with both token counts`),
      h('p.small',`Input tokens: ${tokens(u,'tokens_in')} · output tokens: ${tokens(u,'tokens_out')}`),
      h('p.tiny.muted',`Token basis: ${humanize(u.token_basis)}. Attempts may be format retries or provider fallbacks, not separate host submissions.`),
      h('p.small',h('b',`Estimate: ${money(u.est_usd)}`),` · ${humanize(u.cost_status)}`),
      u.est_usd==null&&u.reported_est_usd!=null?h('p.small','Gateway reported '+money(u.reported_est_usd)+'; excluded from the subtotal because token coverage is incomplete, inconsistent or cached.'):null));
  }
  if(s.requests)box.append(details);
  return box;
}
