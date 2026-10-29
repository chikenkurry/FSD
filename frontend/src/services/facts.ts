import type { PublishedFact } from '@/types/form';

export function factLabel(criterion: string) {
  if (criterion === 'max_cost') return 'Cost per person';
  if (criterion === 'option_rating') return 'Group ratings';
  if (criterion === 'open_on_plan_dates') return 'Open on the plan dates';
  return criterion.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase());
}

export function factValue(fact: Pick<PublishedFact, 'criterion' | 'value' | 'value_type' | 'unit'>, currency: string) {
  const { value, unit } = fact;
  if (fact.value_type === 'decimal' && unit && /^[A-Z]{3}$/.test(unit) && Number.isFinite(Number(value))) {
    try {
      return new Intl.NumberFormat(undefined, { style: 'currency', currency: unit }).format(Number(value));
    } catch {
      /* fall through */
    }
  }
  if (fact.criterion === 'max_cost' && Number.isFinite(Number(value))) {
    try {
      return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(Number(value));
    } catch {
      /* fall through */
    }
  }
  const text = Array.isArray(value)
    ? value.join(', ')
    : typeof value === 'boolean'
      ? value
        ? 'Yes'
        : 'No'
      : String(value ?? '');
  return unit && !/^[A-Z]{3}$/.test(unit) ? `${text} ${unit}` : text;
}

function web(url: unknown) {
  if (typeof url !== 'string') return '';
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : '';
  } catch {
    return '';
  }
}

// Accepted web claims carry their citations; organiser-typed sources may also be a link.
export function sourceLink(fact: Pick<PublishedFact, 'source' | 'context'>) {
  return web(fact.context?.sources?.[0]?.url) || web(fact.source);
}

export function sourceName(fact: Pick<PublishedFact, 'source' | 'context'>) {
  const title = fact.context?.sources?.[0]?.title;
  if (title) return title;
  try {
    return new URL(sourceLink(fact)).hostname.replace(/^www\./, '');
  } catch {
    return 'Source';
  }
}
