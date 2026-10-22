import type { DecisionOption, Fact, Form, Question } from '@/types/form';

export function factType(q: Question): Fact['valueType'] {
  return q.criterion === 'max_cost' ? 'decimal' : q.type === 'Number' ? 'number' : q.type === 'Boolean' ? 'boolean' : q.type === 'Multiple choice' ? 'tag_set' : 'category';
}
export function factStatus(fact?: Fact) {
  if(fact?.context?.estimated && !fact.context.reviewed)return 'estimated';
  return fact?.status || (fact?.context?.estimated ? 'estimated' : fact?.value.trim() ? 'confirmed' : 'unknown');
}
export function tagValues(value:string):string[]{
  if(value.trim().startsWith('[')){
    try{const parsed:unknown=JSON.parse(value);if(Array.isArray(parsed) && parsed.every(v=>typeof v==='string'))return parsed;}catch{/* Read legacy comma-separated values below. */}
  }
  return value.split(',').map(v=>v.trim()).filter(Boolean);
}
export function validFact(fact: Fact | undefined, q: Question): boolean {
  if (!fact?.value.trim() || fact.context?.stale || fact.valueType !== factType(q)) return false;
  if (fact.valueType === 'boolean') return ['true', 'false'].includes(fact.value);
  if (fact.valueType === 'number') return Number.isFinite(Number(fact.value));
  if (fact.valueType === 'decimal') return /^\d+(\.\d{1,2})?$/.test(fact.value.trim());
  if (q.options.length && ['Single choice', 'Multiple choice', 'Location', 'Budget'].includes(q.type)) {
    const values = fact.valueType === 'tag_set' ? tagValues(fact.value) : [fact.value];
    return values.every(value => q.options.includes(value));
  }
  return true;
}
export function comparisonSignature(form: Form, option: DecisionOption, q: Question) {
  return JSON.stringify([form.currency || 'SGD', form.location.trim(), decisionQuestion(form), option.title.trim(), option.summary || '',option.identity?.source_url?.trim() || '',option.identity?.place_id || '',option.identity?.kind || '',
    q.criterion, q.title, q.type, q.role, q.options.map(c => c.trim()).filter(Boolean), q.unit, q.scale]);
}
export function decisionQuestion(form:Form){return form.decisionQuestion?.trim() || ({Event:'Where should we go?',Travel:'Where should we travel?',Work:'Which option should the team choose?'} as Record<string,string>)[form.category] || 'Which option should we choose?';}
export function overviewSignature(form:Form,option:DecisionOption){return JSON.stringify([decisionQuestion(form),form.category,form.location.trim(),form.currency || 'SGD',option.title.trim(),option.identity?.source_url?.trim() || '',option.identity?.place_id || '',option.identity?.kind || '']);}
