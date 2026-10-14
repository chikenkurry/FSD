export type FormStatus = 'Draft' | 'Collecting' | 'Reviewing' | 'Confirmed' | 'Archived';

export interface Question {
  title: string;
  description: string;
  type: 'Multiple choice' | 'Short answer' | 'Single choice' | 'Duration' | 'Location' | 'Budget';
  options: string[];
}

export interface Form {
  id: number;
  // name?: string;
  title: string;
  description: string;
  category: string;
  state: FormStatus;
  membersCount?: number;
  createdBy?: string;
  questions: Question[];
}

export interface LoginPayload {
  username: string;
  password: string;
  rememberMe?: boolean;
}