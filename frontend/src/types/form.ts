export type FormStatus = 'Draft' | 'Collecting' | 'Reviewing' | 'Confirmed' | 'Archived';

export interface Question {
  id?: string;
  criterion?: string;
  role?: 'soft' | 'hard' | 'informational';
  unit?: string;
  scale?: number;
  allowCustomSuggestions?: boolean;
  title: string;
  description: string;
  isRequired?: boolean;
  sortOrder?: number;
  type: 'Multiple choice' | 'Short answer' | 'Single choice' | 'Duration' | 'Location' | 'Budget' | 'Number' | 'Boolean';
  options: string[]; // options list or JSON metadata string
  metadata?: {
    currency?: string;
    allowCustomSuggestions?: boolean;
    minDate?: string;
    maxDate?: string;
  }
}

export interface Form {
  id: string;
  roundId?: string;
  inviteToken?: string;
  currency?: string;
  decisionOptions?: DecisionOption[];
  // name?: string;
  title: string;
  // The question members help answer, e.g. “Where should we celebrate?”
  decisionQuestion?: string;
  description: string;
  category: string;
  state: FormStatus;
  startDateRange: string;
  endDateRange: string;
  location: string;
  membersCount?: number;
  createdBy?: string;
  questions: Question[];
  // Set once a publish request has been sent, so a retry resumes it instead of editing.
  publishAttempted?: boolean;
  removedOptionIds?: string[];
  removedQuestionIds?: string[];
}

export interface LoginPayload {
  username: string;
  password: string;
  rememberMe?: boolean;
}

export interface Fact { criterion: string; value: string; valueType: 'category' | 'number' | 'boolean' | 'tag_set' | 'decimal'; unit: string; source: string; context?: FactContext }
// Provenance written by Planning when an organiser accepts a web-sourced claim.
export interface FactContext { claim_id?: string; sources?: { url: string; title?: string }[]; source_text?: string; retrieved_at?: string; qualifier?: string; [key: string]: unknown }
export type OptionKind = 'place' | 'destination' | 'event' | 'activity' | 'other';
export interface DecisionOption { id?: string; title: string; facts: Fact[]; identity?: { source_url?: string; place_id?: string; kind?: OptionKind }; overview?: Overview; summary?: string; brief?: Brief }
// The stored, publishable part of an overview: written by web search or AI, never copied from Google Places.
export interface Brief { source: 'web_search' | 'ai_general'; summary: string; highlights: string[]; price_note: string; when: string; where: string; sources: { url: string; title?: string }[] }
// Display-only research about an option. Place content is fetched live and never stored.
export interface Overview { source: 'google_places' | 'web_search' | 'ai_general'; name?: string; summary?: string; review_summary?: string; review_disclosure?: string;
  highlights?: string[]; rating?: number | null; rating_count?: number | null; price_level?: number | null; price_note?: string; when?: string; where?: string;
  address?: string; kind_label?: string; website?: string; maps_url?: string; place_id?: string | null; opening_hours?: string[];
  photos?: { name: string; attributions: { name: string; uri: string }[] }[]; sources?: { url: string; title?: string }[]; tagline?: string }
export interface DraftedQuestion { title: string; help: string; type: 'single' | 'multiple' | 'yes_no' | 'budget'; role: 'preference' | 'requirement'; criterion: string; choices: string[] }
export interface FitFact { option: string; criterion: string; values: string[]; reason: string; sources: { url: string; title?: string }[] }
export interface ResearchRun<T> { run_id: string; status: string; issues: { code: string }[]; research?: T }
export interface PublishedFact { criterion: string; value: unknown; value_type?: string; unit?: string | null; status?: string; source?: string; context?: FactContext }
export interface FactClaim { claim_id: string; option_id: string; attribute_id: string; value_type: Fact['valueType']; value: unknown; unit: string | null; qualifier: string; source_text: string; valid_until: string | null; sources: { url: string; title?: string }[] }
export interface FactCollectionRun { run_id: string; status: string; issues: { code: string; fields?: string[] }[]; collection?: { claims: FactClaim[]; issues: { code: string }[]; grounding?: { searchEntryPoint?: { renderedContent?: string } } } }
export interface Session { id: string; username: string; session_token: string }
export interface PlanRow { id: string; title: string; description?: string; category: string; state: string; created_by_user_id: string; members_count?: number; organiser_name?: string }
export interface Round { id: string; round_number: number }
export type Choice = string | { choice_id: string; label: string };
export interface PublishedQuestion { question_id: string; label: string; role?: string; criterion?: string; answer_format?: string; choices?: Choice[]; mapping?: { value_type?: string; unit?: string }; required?: boolean }
export interface Snapshot { plan_id: string; round_id: string; option_revision: number; decision_question: string; currency: string; currency_minor_digits: number; execution_mode: string; questions: PublishedQuestion[]; options: { option_id: string; title: string; description?: string; facts?: PublishedFact[]; identity?: { place_id?: string; kind?: OptionKind; source_url?: string }; brief?: Brief }[] }
export interface Answer { question_id: string; value: unknown; reviewed_revision?: number; confirmed_requirements?: unknown[] }
export interface Draft {
  revision: number; status: string; acknowledgedOptionRevision: number;
  availability: { startAt: string; endAt: string }[]; budget: { kind: string; capMinor?: number | null };
  activityAnswers: { activityId: string; kind: string; rating?: number | null }[];
  answers: Answer[]; privateNote: string | null; round: { state: string };
}
export interface Constraint { source_question_id: string; attribute_id: string; required_value: unknown; constraint_rule: string; unit?: string; kind?: string; status?: string }
export interface Review { status: string; response_revision: number; run_id: string; constraints: Constraint[]; preferences?: { attribute_id: string; kind: string; preferred_value?: unknown }[]; issues: { code: string; message?: string }[] }
export interface Candidate { candidate_id: string; title: string; rank: number; primary_objective_tie_size: number; group_score: number; minimum_member_score: number; average_member_score: number; start_at?: string; end_at?: string; estimated_cost_minor?: number | null; currency?: string; currency_minor_digits?: number; tradeoffs?: string[] }
export interface Run { run_id: string; status: string; issues: { code: string }[]; fact_requests?: { option_id: string; attribute_id: string }[]; recommendation_view: { recommendation: Candidate | null; alternatives: Candidate[]; pareto_alternatives: Candidate[]; next_action: string | null; unavailable_candidates: { candidate_id: string; title: string; status: string }[] } }
export interface Selection { run_id: string; candidate_id: string; selection_version: number }
