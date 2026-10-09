/** Value sets shared by the HTTP DTOs, the domain and the persistence adapters. */
export const BUDGET_KINDS = ['UNANSWERED', 'CAP', 'UNLIMITED'] as const;
export const ANSWER_KINDS = ['RATING', 'NO_PREFERENCE', 'CANNOT_JOIN', 'NEEDS_INFO'] as const;

export type BudgetKindValue = (typeof BUDGET_KINDS)[number];
export type AnswerKindValue = (typeof ANSWER_KINDS)[number];
export type ResponseStatusValue = 'DRAFT' | 'SUBMITTED';
