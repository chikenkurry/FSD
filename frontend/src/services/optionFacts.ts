import type { DecisionOption, Fact, FactDefinition, Form, Question } from '@/types/form';

export function factType(q: Question): Fact['valueType'] {
  return q.criterion === 'max_cost' ? 'decimal' : q.valueType || (q.type === 'Number' ? 'number' : q.type === 'Boolean' ? 'boolean' : q.type === 'Multiple choice' ? 'tag_set' : 'category');
}
export function factStatus(fact?: Fact) {
  if (fact?.context?.estimated && !fact.context.reviewed && fact.context.verification !== 'grounded_search') return 'estimated';
  return fact?.status || (fact?.context?.estimated ? 'estimated' : fact?.value.trim() ? 'confirmed' : 'unknown');
}
export function tagValues(value: string): string[] {
  if (value.trim().startsWith('[')) {
    try { const parsed: unknown = JSON.parse(value); if (Array.isArray(parsed) && parsed.every(v => typeof v === 'string')) return parsed; } catch { /* Legacy comma-separated values. */ }
  }
  return value.split(',').map(v => v.trim()).filter(Boolean);
}
export function definitionFor(q: Question): FactDefinition {
  return { criterion: q.criterion!, valueType: factType(q), unit: q.unit || '' };
}
export function factDefinitions(form: Form): FactDefinition[] {
  const definitions = new Map<string, FactDefinition>();
  const active = form.questions.filter(q => q.role !== 'informational');
  for (const q of active) if (q.criterion && q.criterion !== 'preferences') definitions.set(q.criterion, definitionFor(q));
  // A general written question may refer to any already researched attribute.
  if (active.some(q => q.criterion === 'preferences')) for (const o of form.decisionOptions || []) for (const f of o.facts) {
    if (!definitions.has(f.criterion)) definitions.set(f.criterion, { criterion: f.criterion, valueType: f.valueType, unit: f.unit });
  }
  return [...definitions.values()];
}
export function validFact(fact: Fact | undefined, definition: FactDefinition): boolean {
  if (!fact?.value.trim() || fact.context?.stale || fact.valueType !== definition.valueType || fact.unit !== definition.unit) return false;
  if (typeof fact.context?.valid_until === 'string' && !(Date.parse(fact.context.valid_until) > Date.now())) return false;
  if (fact.context?.qualifier && fact.context.qualifier !== 'exact' && !fact.context.corrected) return false;
  if (fact.valueType === 'boolean') return ['true', 'false'].includes(fact.value);
  if (fact.valueType === 'number') return Number.isFinite(Number(fact.value));
  if (fact.valueType === 'decimal') return /^\d+(\.\d{1,2})?$/.test(fact.value.trim());
  if (fact.valueType === 'tag_set') return tagValues(fact.value).length > 0;
  return true;
}
// Facts belong to an option/attribute, not a question's wording or answer choices.
export function factSignature(form: Form, option: DecisionOption, definition: FactDefinition) {
  return JSON.stringify([form.location.trim(), option.title.trim(), option.summary || '', option.identity?.source_url?.trim() || '', option.identity?.place_id || '', option.identity?.kind || '',
    definition.criterion, definition.valueType, definition.unit]);
}
export function decisionQuestion(form: Form) { return form.decisionQuestion?.trim() || ({ Event: 'Where should we go?', Travel: 'Where should we travel?', Work: 'Which option should the team choose?' } as Record<string, string>)[form.category] || 'Which option should we choose?'; }
export function overviewSignature(form: Form, option: DecisionOption) { return JSON.stringify([decisionQuestion(form), form.category, form.location.trim(), form.currency || 'SGD', option.title.trim(), option.identity?.source_url?.trim() || '', option.identity?.place_id || '', option.identity?.kind || '']); }
