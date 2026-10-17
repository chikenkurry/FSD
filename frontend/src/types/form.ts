export type FormStatus = 'Draft' | 'Collecting' | 'Reviewing' | 'Confirmed' | 'Archived';

export interface Question {
  title: string;
  description: string;
  isRequired?: boolean;
  sortOrder?: number;
  type: 'Multiple choice' | 'Short answer' | 'Single choice' | 'Duration' | 'Location' | 'Budget';
  options: string[]; // options list or JSON metadata string
  metadata?: {
    currency?: string;
    allowCustomSuggestions?: boolean;
    minDate?: string;
    maxDate?: string;
  }
}

export interface Form {
  id: number;
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