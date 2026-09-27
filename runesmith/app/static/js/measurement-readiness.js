// A saved-report assessment, never a live source or business-success badge.
import {h} from './core.js';

const AGE = {not_configured:'No data-age rule',within_limit:'Newest included timestamp within age rule',expired:'Data-age limit exceeded',
  future:'Future data timestamp',unknown:'Data age unknown',invalid_policy:'Invalid data-age rule'};
const SOURCE = {matching_paste:'Selected paste matches',superseded:'New paste awaits measurement',
  unknown:'Input identity unknown',not_rechecked:'Local file not rechecked',unavailable:'Connector unavailable'};

export function measurementReadiness(assessment) {
  if (!assessment) return h('p.small.muted','Report readiness is unavailable; do not infer current conditions from this historical receipt.');
  return h('div.measurement-readiness.mt-8',
    h('div.row.wrap',h('b.small','Report readiness'),h('span.badge',AGE[assessment.age_status]||'Data age unknown'),
      h('span.badge',SOURCE[assessment.source_status]||'Input identity unknown')),
    h('p.small', {class:assessment.usable?'small muted':'small warn'},assessment.detail),
    assessment.qualified_threshold_met!==null&&assessment.qualified_threshold_met!==undefined
      ?h('p.small',`Age-qualified saved-report threshold: ${assessment.qualified_threshold_met?'met':'not met'}. Not live verification or goal acceptance.`):null,
    h('p.tiny.faint',assessment.scope),
    h('p.tiny.faint','Readiness is as of the last refresh; an open page is not a live source monitor.'));
}
