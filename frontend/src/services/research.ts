// Organiser research: overviews start in the background as soon as options are saved,
// questions are drafted from them, and each ranking question's own choices are filled
// in per option. Every result is a suggestion the organiser can change before publishing.
import { reactive, ref, onScopeDispose } from 'vue';
import type { Brief, DecisionOption, DraftedQuestion, Fact, FitFact, Form, OptionKind, Overview, Question } from '@/types/form';
import { apiService, ApiError } from './api';

export interface OptionResearch { status: 'idle' | 'loading' | 'done' | 'failed'; title: string; link: string; context?: string }
export interface ResearchState {
  options: Record<string, OptionResearch>;
  questions: 'idle' | 'loading' | 'done' | 'failed';
  fit: 'idle' | 'loading' | 'done' | 'failed';
  fitting: Set<string>;
  message: string;
}

const messages: Record<string, string> = {
  FACT_COLLECTOR_NOT_CONFIGURED: 'AI research isn’t set up on this server (GEMINI_API_KEY is missing), so add details and questions yourself.',
  UPSTREAM_UNAVAILABLE: 'AI research is unavailable right now. You can carry on and fill things in yourself.',
  EXECUTION_DEADLINE_EXCEEDED: 'AI research took too long. You can try again or carry on yourself.',
};
export function researchMessage(error: unknown) {
  const code = error instanceof ApiError ? error.code : '';
  if (messages[code]) return messages[code];
  if (code.startsWith('GEMINI_') || code.startsWith('PLACES_')) return 'An AI provider rejected the request. Check the API keys in FSD/.env.';
  return 'AI research couldn’t finish. You can try again or carry on yourself.';
}

export function optionKey(option: DecisionOption) { return option.id || option.title; }

export function useResearch(form: Form, saveDraft: () => Promise<void>) {
  const state = reactive<ResearchState>({ options: {}, questions: 'idle', fit: 'idle', fitting: new Set(), message: '' });
  const signal = { cancelled: false };
  onScopeDispose(() => { signal.cancelled = true; });
  // Bumped once place IDs are saved, so cards know their photos can be loaded.
  const revision = ref(0);
  const options = () => (form.decisionOptions || []).filter(o => o.title.trim());
  const context = () => ({ decision_question: form.decisionQuestion?.trim() || '', category: form.category, region: form.location.trim(), currency: form.currency || 'SGD' });

  // Only new or renamed options are looked up again.
  function stale(option: DecisionOption) {
    const row = state.options[optionKey(option)];
    return !row || row.status === 'failed' || row.title !== option.title.trim() || row.link !== (option.identity?.source_url || '').trim() || row.context !== JSON.stringify(context());
  }
  async function overviews() {
    const wanted = options().filter(stale);
    if (!wanted.length) return;
    await saveDraft();
    for (const o of wanted) state.options[optionKey(o)] = { status: 'loading', title: o.title.trim(), link: (o.identity?.source_url || '').trim(), context: JSON.stringify(context()) };
    // One job per option, in parallel, so each card appears as soon as it is ready.
    await Promise.all(wanted.map(async option => {
      const key = optionKey(option);
      try {
        const result = await apiService.research<{ options: { key: string; kind: OptionKind; place_id: string | null; overview: Overview | null }[] }>(form.roundId!, 'overviews', {
          ...context(), options: [{ key, title: option.title.trim(), source_url: option.identity?.source_url?.trim() || '', kind: option.identity?.kind, place_id: option.identity?.place_id }] }, signal);
        if (signal.cancelled) return;
        const row = result.options[0];
        option.identity = { ...option.identity, kind: row?.kind, ...(row?.place_id ? { place_id: row.place_id } : {}) };
        option.overview = row?.overview || undefined;
        // Members see this summary; place details are fetched live instead of stored.
        // The web-written summary is stored for members; Google Places content stays live-only.
        option.summary = row?.overview?.summary || '';
        option.brief = brief(row?.overview);
        state.options[key]!.status = 'done';
      } catch (error) {
        state.options[key]!.status = 'failed';
        state.message = researchMessage(error);
      }
    }));
    // Planning serves place photos only for place IDs saved on this plan.
    if (wanted.some(o => o.identity?.place_id)) await saveDraft().catch(() => undefined);
    revision.value++;
  }

  async function draftQuestions(): Promise<Question[]> {
    state.questions = 'loading'; state.message = '';
    try {
      const { questions } = await apiService.research<{ questions: DraftedQuestion[] }>(form.roundId!, 'questions', {
        ...context(), options: options().map(o => ({ title: o.title.trim(), summary: (o.brief?.summary || o.overview?.summary || o.overview?.review_summary || '').slice(0, 1500) })) }, signal);
      if (signal.cancelled) return [];
      state.questions = 'done';
      return questions.map(q => toQuestion(q, form.currency || 'SGD'));
    } catch (error) {
      state.questions = 'failed'; state.message = researchMessage(error);
      return [];
    }
  }

  // Asks only for the facts each question still lacks, so new questions trigger new lookups.
  let fitWork: Promise<void> | undefined;
  async function fit(questions: Question[]) {
    if (fitWork) await fitWork;
    if (signal.cancelled) return;
    const work = runFit(questions);
    fitWork = work;
    try { await work; } finally { if (fitWork === work) fitWork = undefined; }
  }
  async function runFit(questions: Question[]) {
    const isBudget = (q: Question) => q.criterion === 'max_cost' && q.type === 'Number';
    const askable = questions.filter(q => q.role !== 'informational' && q.criterion && (isBudget(q) || ['Single choice', 'Multiple choice', 'Boolean'].includes(q.type))
      && (isBudget(q) || q.type === 'Boolean' || q.options.filter(c => c.trim()).length >= 2)
      && options().some(o => !o.facts.some(f => f.criterion === q.criterion && f.value.trim())));
    if (!askable.length) return;
    state.fit = 'loading'; state.message = '';
    for (const q of askable) state.fitting.add(q.criterion!);
    try {
      await saveDraft();
      const list = options();
      const { facts } = await apiService.research<{ facts: FitFact[] }>(form.roundId!, 'fit', {
        ...context(), options: list.map(o => ({ key: optionKey(o), title: o.title.trim() })),
        summaries: Object.fromEntries(list.map(o => [optionKey(o), o.brief?.summary || o.overview?.summary || o.overview?.review_summary || ''])),
        questions: askable.map(q => ({ criterion: q.criterion, title: q.title, type: isBudget(q) ? 'budget' : q.type === 'Multiple choice' ? 'multiple' : q.type === 'Boolean' ? 'yes_no' : 'single',
          choices: q.type === 'Boolean' || isBudget(q) ? [] : q.options.map(c => c.trim()).filter(Boolean) })) }, signal);
      if (signal.cancelled) return;
      for (const fact of facts) {
        const option = list.find(o => optionKey(o) === fact.option);
        const question = askable.find(q => q.criterion === fact.criterion);
        if (!option || !question || option.facts.some(f => f.criterion === fact.criterion && f.value.trim() && !f.context?.estimated)) continue;
        option.facts = [...option.facts.filter(f => f.criterion !== fact.criterion), estimate(fact, question, form.currency || 'SGD')];
      }
      state.fit = 'done';
      const incomplete = askable.filter(q => list.some(o => !o.facts.some(f => f.criterion === q.criterion && f.value.trim())));
      if (incomplete.length) state.message = 'Research finished without enough evidence for some comparisons. Retry the missing facts or change those questions to context only.';
    } catch (error) {
      state.fit = 'failed'; state.message = researchMessage(error);
    } finally {
      for (const q of askable) state.fitting.delete(q.criterion!);
    }
  }
  return { state, revision, overviews, draftQuestions, fit };
}

// Our own (web or AI) description, safe to store and publish with the option.
function brief(overview?: Overview | null): Brief | undefined {
  if (!overview) return undefined;
  return { source: overview.source === 'ai_general' ? 'ai_general' : 'web_search', summary: overview.summary || '', highlights: overview.highlights || [],
    price_note: overview.price_note || '', when: overview.when || '', where: overview.where || '', sources: (overview.sources || []).slice(0, 3) };
}

function toQuestion(d: DraftedQuestion, currency: string): Question {
  const base = { title: d.title, description: d.help, criterion: d.criterion, role: d.role === 'requirement' ? 'hard' : 'soft' } as const;
  if (d.type === 'budget') return { ...base, role: 'hard', type: 'Number', unit: currency, options: [] };
  if (d.type === 'yes_no') return { ...base, type: 'Boolean', options: [] };
  return { ...base, type: d.type === 'multiple' ? 'Multiple choice' : 'Single choice', options: d.choices };
}

// AI placements become option facts marked as estimates, keeping their reason and sources.
function estimate(fact: FitFact, question: Question, currency: string): Fact {
  const cost = fact.criterion === 'max_cost';
  const valueType: Fact['valueType'] = cost ? 'decimal' : question.type === 'Multiple choice' ? 'tag_set' : question.type === 'Boolean' ? 'boolean' : 'category';
  return { criterion: fact.criterion, value: fact.values.join(', '), valueType, unit: cost ? currency : '', source: fact.sources[0]?.url || 'AI estimate',
    context: { estimated: true, reason: fact.reason, sources: fact.sources } };
}
