// Organiser research: overviews start in the background as soon as options are saved,
// facts are collected as reusable attributes. Question choices and member answers
// never enter the fact collector. Exact cited facts can be used automatically;
// the organiser can correct them while reviewing the options.
import { reactive, ref, onScopeDispose } from 'vue';
import type {
  Brief,
  DecisionOption,
  DraftedQuestion,
  Fact,
  FactDefinition,
  ResearchedFact,
  Form,
  OptionKind,
  Overview,
  Question,
} from '@/types/form';
import { apiService, ApiError } from './api';
import { operationId } from './ids';
import { factSignature, decisionQuestion, overviewSignature, validFact } from './optionFacts';

export interface OptionResearch {
  status: 'idle' | 'loading' | 'done' | 'failed';
  title: string;
  link: string;
  context?: string;
  refreshId?: string;
}
export interface ResearchState {
  options: Record<string, OptionResearch>;
  questions: 'idle' | 'loading' | 'done' | 'failed';
  facts: 'idle' | 'loading' | 'done' | 'failed';
  message: string;
}

const messages: Record<string, string> = {
  FACT_COLLECTOR_NOT_CONFIGURED:
    'AI research isn’t set up on this server (GEMINI_API_KEY is missing), so add details and questions yourself.',
  UPSTREAM_UNAVAILABLE: 'AI research is unavailable right now. You can carry on and fill things in yourself.',
  EXECUTION_DEADLINE_EXCEEDED: 'AI research took too long. You can try again or carry on yourself.',
};
export function researchMessage(error: unknown) {
  const code = error instanceof ApiError ? error.code : '';
  if (messages[code]) return messages[code];
  if (code.startsWith('GEMINI_') || code.startsWith('PLACES_'))
    return 'An AI provider rejected the request. Check the API keys in FSD/.env.';
  return 'AI research couldn’t finish. You can try again or carry on yourself.';
}

export function optionKey(option: DecisionOption) {
  return option.id || option.title;
}

export function useResearch(form: Form, saveDraft: () => Promise<void>) {
  const state = reactive<ResearchState>({ options: {}, questions: 'idle', facts: 'idle', message: '' });
  const signal = { cancelled: false };
  const cancel = () => {
    signal.cancelled = true;
  };
  window.addEventListener('beforeunload', cancel);
  onScopeDispose(() => {
    cancel();
    window.removeEventListener('beforeunload', cancel);
  });
  // Bumped once place IDs are saved, so cards know their photos can be loaded.
  const revision = ref(0);
  const options = () => (form.decisionOptions || []).filter((o) => o.title.trim());
  const context = () => ({
    decision_question: decisionQuestion(form),
    category: form.category,
    region: form.location.trim(),
    currency: form.currency || 'SGD',
  });

  // Only new or renamed options are looked up again.
  function stale(option: DecisionOption) {
    const row = state.options[optionKey(option)];
    if (
      !row &&
      (option.brief?.input_signature === overviewSignature(form, option) ||
        (option.brief?.source === 'organiser' && !option.brief.input_signature))
    )
      return false;
    return (
      !row ||
      row.status === 'failed' ||
      row.status === 'loading' ||
      row.title !== option.title.trim() ||
      row.link !== (option.identity?.source_url || '').trim() ||
      row.context !== JSON.stringify(context())
    );
  }
  async function overviews(refresh?: DecisionOption) {
    const wanted = refresh ? [refresh] : options().filter(stale);
    if (!wanted.length) return;
    await saveDraft();
    for (const o of wanted)
      state.options[optionKey(o)] = {
        status: 'loading',
        title: o.title.trim(),
        link: (o.identity?.source_url || '').trim(),
        context: JSON.stringify(context()),
        refreshId: refresh ? operationId() : state.options[optionKey(o)]?.refreshId,
      };
    // One job per option, in parallel, so each card appears as soon as it is ready.
    await Promise.all(
      wanted.map(async (option) => {
        const key = optionKey(option);
        const fingerprint = () =>
          JSON.stringify([
            option.title.trim(),
            option.identity?.source_url || '',
            option.identity?.kind,
            option.identity?.place_id,
            context(),
          ]);
        const input = fingerprint();
        const refreshId = state.options[key]?.refreshId;
        const previousSummary = option.summary;
        try {
          const result = await apiService.research<{
            options: { key: string; kind: OptionKind; place_id: string | null; overview: Overview | null }[];
          }>(
            form.roundId!,
            'overviews',
            {
              ...context(),
              refresh_id: state.options[key]?.refreshId,
              options: [
                {
                  key,
                  title: option.title.trim(),
                  source_url: option.identity?.source_url?.trim() || '',
                  kind: option.identity?.kind,
                  place_id: option.identity?.place_id,
                },
              ],
            },
            signal,
          );
          if (signal.cancelled || form.publishAttempted || form.state !== 'Draft') return;
          if (
            input !== fingerprint() ||
            previousSummary !== option.summary ||
            refreshId !== state.options[key]?.refreshId
          ) {
            if (refreshId === state.options[key]?.refreshId) state.options[key]!.status = 'failed';
            state.message =
              'The option changed during research. Your edits were kept; research again to update the overview.';
            return;
          }
          const row = result.options[0];
          option.identity = {
            ...option.identity,
            kind: row?.kind,
            ...(row?.place_id ? { place_id: row.place_id } : {}),
          };
          option.overview = row?.overview || undefined;
          // Members see this summary; place details are fetched live instead of stored.
          // The web-written summary is stored for members; Google Places content stays live-only.
          option.summary = row?.overview?.summary || '';
          option.brief = brief(row?.overview);
          if (option.brief) option.brief.input_signature = overviewSignature(form, option);
          state.options[key]!.status = 'done';
        } catch (error) {
          state.options[key]!.status = 'failed';
          state.message = researchMessage(error);
        }
      }),
    );
    // Planning serves place photos only for place IDs saved on this plan.
    if (wanted.some((o) => o.identity?.place_id)) await saveDraft().catch(() => undefined);
    revision.value++;
  }

  async function draftQuestions(): Promise<Question[]> {
    state.questions = 'loading';
    state.message = '';
    try {
      const { questions } = await apiService.research<{ questions: DraftedQuestion[] }>(
        form.roundId!,
        'questions',
        {
          ...context(),
          options: options().map((o) => ({
            title: o.title.trim(),
            summary: (o.brief?.summary || o.overview?.summary || o.overview?.review_summary || '').slice(0, 1500),
          })),
        },
        signal,
      );
      if (signal.cancelled || form.publishAttempted || form.state !== 'Draft') return [];
      state.questions = 'done';
      return questions.map((q) => toQuestion(q, form.currency || 'SGD'));
    } catch (error) {
      state.questions = 'failed';
      state.message = researchMessage(error);
      return [];
    }
  }

  // One active fact job per creator. Further calls recheck missing attributes
  // after it settles, preserving edits and avoiding duplicate work on navigation.
  let factWork: Promise<void> | undefined;
  async function facts(definitions: FactDefinition[]) {
    if (factWork) await factWork;
    if (signal.cancelled) return;
    const work = runFacts(definitions);
    factWork = work;
    try {
      await work;
    } finally {
      if (factWork === work) factWork = undefined;
    }
  }
  async function runFacts(definitions: FactDefinition[], refresh?: { option: DecisionOption; note: string }) {
    const list = refresh ? [refresh.option] : options();
    const wanted = definitions.filter(
      (d) =>
        refresh ||
        list.some((o) => {
          const f = o.facts.find((f) => f.criterion === d.criterion);
          return !f?.value.trim() || f.context?.stale || f.valueType !== d.valueType || f.unit !== d.unit;
        }),
    );
    if (!wanted.length) return;
    if (form.publishAttempted || form.state !== 'Draft') return;
    state.facts = 'loading';
    state.message = '';
    try {
      for (const o of list)
        for (const d of wanted) {
          let fact = o.facts.find((f) => f.criterion === d.criterion);
          if (!fact) {
            fact = {
              criterion: d.criterion,
              value: '',
              valueType: d.valueType,
              unit: d.unit,
              source: '',
              status: 'unknown',
            };
            o.facts.push(fact);
          }
          fact.context = { ...fact.context, research_pending: true };
        }
      await saveDraft();
      const key = (o: DecisionOption, d: FactDefinition) => `${optionKey(o)}:${d.criterion}`;
      const signatures = new Map(
        list.flatMap((o) => wanted.map((d) => [key(o, d), factSignature(form, o, d)] as const)),
      );
      const before = new Map(
        list.flatMap((o) =>
          wanted.map((d) => [key(o, d), JSON.stringify(o.facts.find((f) => f.criterion === d.criterion))] as const),
        ),
      );
      const pending = refresh?.option.facts.find((f) => f.criterion === wanted[0]?.criterion)?.context
        ?.research_refresh_id;
      const result = await apiService.research<{ facts: ResearchedFact[]; issues: { code: string }[] }>(
        form.roundId!,
        'facts',
        {
          region: form.location.trim(),
          currency: form.currency || 'SGD',
          refresh_id: pending,
          ...(refresh ? { correction: refresh.note.slice(0, 1000) } : {}),
          options: list.map((o) => ({
            key: optionKey(o),
            title: o.title.trim(),
            source_url: o.identity?.source_url || '',
          })),
          attributes: wanted.map((d) => ({ criterion: d.criterion, value_type: d.valueType, unit: d.unit || null })),
        },
        signal,
      );
      if (signal.cancelled || form.publishAttempted || form.state !== 'Draft') return;
      for (const option of list)
        for (const definition of wanted) {
          const current = option.facts.find((f) => f.criterion === definition.criterion);
          if (
            !refresh &&
            current?.value.trim() &&
            !current.context?.stale &&
            current.valueType === definition.valueType &&
            current.unit === definition.unit
          )
            continue;
          if (
            signatures.get(key(option, definition)) !== factSignature(form, option, definition) ||
            before.get(key(option, definition)) !== JSON.stringify(current)
          )
            continue;
          const claims = result.facts.filter(
            (f) =>
              f.option === optionKey(option) &&
              f.criterion === definition.criterion &&
              f.value_type === definition.valueType &&
              (f.unit || '') === definition.unit,
          );
          const unique = [...new Map(claims.map((c) => [JSON.stringify([c.value, c.context.qualifier]), c])).values()];
          const merged =
            definition.valueType === 'tag_set' &&
            unique.length > 1 &&
            unique.every((c) => c.context.qualifier !== 'conditions')
              ? [
                  {
                    ...unique[0]!,
                    value: [...new Set(unique.flatMap((c) => (Array.isArray(c.value) ? c.value : [String(c.value)])))],
                    sources: [...new Map(unique.flatMap((c) => c.sources).map((s) => [s.url, s])).values()],
                  },
                ]
              : unique;
          const row: Fact =
            merged.length === 1
              ? researchedFact(merged[0]!, signatures.get(key(option, definition))!)
              : {
                  ...(current || {
                    criterion: definition.criterion,
                    value: '',
                    valueType: definition.valueType,
                    unit: definition.unit,
                    source: '',
                  }),
                  status: 'estimated',
                  context: {
                    ...current?.context,
                    reviewed: false,
                    alternatives: unique,
                    reason: unique.length
                      ? 'Sources disagree. Choose a supported finding or correct this fact.'
                      : 'No cited evidence was found. Your existing value was kept.',
                    input_signature: signatures.get(key(option, definition)),
                  },
                };
          if (merged.length === 1 && validFact(row, definition)) {
            row.status = 'confirmed';
            row.context = { ...row.context, verification: 'grounded_search' };
          }
          option.facts = [...option.facts.filter((f) => f.criterion !== definition.criterion), row];
        }
      state.facts = 'done';
      if (!result.facts.length)
        state.message =
          'No supported facts were found. You can still publish; Decision will try to supplement missing evidence when processing answers.';
    } catch (error) {
      state.facts = 'failed';
      state.message = researchMessage(error);
    } finally {
      // A leaving tab must retain its pending operation for refresh recovery.
      if (!signal.cancelled) {
        for (const o of list)
          for (const f of o.facts)
            if (wanted.some((d) => d.criterion === f.criterion) && f.context) delete f.context.research_pending;
        if (refresh)
          for (const f of refresh.option.facts)
            if (wanted.some((d) => d.criterion === f.criterion) && f.context) delete f.context.research_refresh_id;
      }
    }
  }
  async function researchAgain(option: DecisionOption, definition: FactDefinition, note = '') {
    if (factWork) await factWork;
    let fact = option.facts.find((f) => f.criterion === definition.criterion);
    if (!fact) {
      fact = {
        criterion: definition.criterion,
        value: '',
        valueType: definition.valueType,
        unit: definition.unit,
        source: '',
        status: 'unknown',
      };
      option.facts.push(fact);
    }
    fact.status = 'estimated';
    fact.context = {
      ...fact.context,
      reviewed: false,
      research_refresh_id: fact.context?.research_refresh_id || operationId(),
      research_note: note.slice(0, 1000),
    };
    const work = runFacts([definition], { option, note });
    factWork = work;
    try {
      await work;
    } finally {
      if (factWork === work) factWork = undefined;
    }
  }
  return { state, revision, overviews, draftQuestions, facts, researchAgain };
}

export function researchedFact(fact: ResearchedFact, signature: string): Fact {
  return {
    criterion: fact.criterion,
    value: fact.value_type === 'tag_set' ? JSON.stringify(fact.value) : String(fact.value),
    valueType: fact.value_type,
    unit: fact.unit || '',
    source: fact.sources[0]?.url || '',
    status: 'estimated',
    context: {
      ...fact.context,
      estimated: true,
      reviewed: false,
      sources: fact.sources,
      retrieved_at: fact.retrieved_at,
      input_signature: signature,
    },
  };
}

// Our own (web or AI) description, safe to store and publish with the option.
function brief(overview?: Overview | null): Brief | undefined {
  if (!overview) return undefined;
  return {
    source: overview.source === 'ai_general' ? 'ai_general' : 'web_search',
    summary: overview.summary || '',
    highlights: overview.highlights || [],
    price_note: overview.price_note || '',
    when: overview.when || '',
    where: overview.where || '',
    sources: (overview.sources || []).slice(0, 3),
  };
}

function toQuestion(d: DraftedQuestion, currency: string): Question {
  const weight = d.weight || 'normal';
  const base = {
    title: d.title,
    description: d.help,
    criterion: d.criterion,
    role: d.role === 'requirement' ? 'hard' : 'soft',
    valueType: d.value_type,
    weightLevel: weight,
    suggestedWeight: weight,
  } as const;
  if (d.type === 'budget') return { ...base, role: 'hard', type: 'Number', unit: currency, options: [] };
  if (d.type === 'yes_no') return { ...base, type: 'Boolean', options: [] };
  if (d.type === 'written') return { ...base, type: 'Short answer', options: [] };
  return { ...base, type: d.type === 'multiple' ? 'Multiple choice' : 'Single choice', options: d.choices };
}
