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
  description: string;
  category: string;
  state: FormStatus;
  startDateRange: string;
  endDateRange: string;
  location: string;
  membersCount?: number;
  createdBy?: string;
  questions: Question[];
}

export interface LoginPayload {
  username: string;
  password: string;
  rememberMe?: boolean;
}

export interface Fact { criterion: string; value: string; valueType: 'category' | 'number' | 'boolean' | 'tag_set' | 'decimal'; unit: string; source: string }
export interface DecisionOption { id?: string; title: string; facts: Fact[] }
export interface Session { id: string; username: string; session_token: string }
export interface PlanRow { id: string; title: string; description?: string; category: string; state: string; created_by_user_id: string; members_count?: number; organiser_name?: string }
export interface Round { id: string; round_number: number }
export type Choice = string | { choice_id: string; label: string };
export interface PublishedQuestion { question_id: string; label: string; role?: string; answer_format?: string; choices?: Choice[]; mapping?: { value_type?: string }; required?: boolean }
export interface Snapshot { plan_id: string; round_id: string; option_revision: number; decision_question: string; currency: string; currency_minor_digits: number; execution_mode: string; questions: PublishedQuestion[]; options: { option_id: string; title: string }[] }
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
