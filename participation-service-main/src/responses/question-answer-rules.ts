import { FieldError } from '../common/api-exception';
import { QuestionAnswerDto, QuestionDefinitionDto } from './question-answer';

export function validJson(value: unknown): boolean {
  try {
    const text = JSON.stringify(value);
    return text !== undefined && text.length <= 16_000;
  } catch {
    return false;
  }
}

export function answeredRequiredQuestions(
  answers: QuestionAnswerDto[],
  questions: QuestionDefinitionDto[],
): boolean {
  const present = new Set(
    answers.filter(answer => isAnswered(answer.value)).map(answer => answer.question_id.toLowerCase()),
  );
  return questions.every(q => !q.required || present.has(q.questionId.toLowerCase()));
}

function isAnswered(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === 'string') return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

export function validateQuestionAnswers(
  answers: QuestionAnswerDto[],
  definitions: QuestionDefinitionDto[],
): FieldError[] {
  const errors: FieldError[] = [];
  const questions = new Map(definitions.map(q => [q.questionId.toLowerCase(), q]));
  const answered = new Set<string>();
  for (const [index, answer] of answers.entries()) {
    const id = answer.question_id.toLowerCase();
    const definition = questions.get(id);
    if (!definition || answered.has(id) || !validJson(answer.value)) {
      errors.push({ field: `answers.${index}`, message: 'Unknown, duplicate or invalid question answer' });
      continue;
    }
    answered.add(id);
    const value = answer.value;
    if (!matchesQuestionValue(value, definition)) {
      errors.push({
        field: `answers.${index}.value`,
        message: 'Value does not match the published question format or choices',
      });
    }
    for (const review of [answer.confirmed_requirement, answer.confirmed_requirements]) {
      if (review !== undefined && !validJson(review)) {
        errors.push({ field: `answers.${index}`, message: 'Invalid confirmation record' });
      }
    }
  }

  return errors;
}

function matchesQuestionValue(value: unknown, definition: QuestionDefinitionDto): boolean {
  if (!matchesFormat(value, definition.answerFormat)) return false;
  if (definition.answerFormat !== 'choice' && definition.answerFormat !== 'multi_choice') return true;
  const choices = (definition.choices ?? []).map(choice =>
    typeof choice === 'object' && choice !== null ? (choice as { choice_id?: unknown }).choice_id : choice,
  );
  const selected = Array.isArray(value) ? value : [value];
  return selected.every(item => choices.includes(item));
}

function matchesFormat(value: unknown, format: string): boolean {
  switch (format) {
    case 'text':
      return typeof value === 'string';
    case 'number':
      return typeof value === 'number' && Number.isFinite(value);
    case 'boolean':
      return typeof value === 'boolean';
    case 'multi_choice':
    case 'date_intervals':
      return Array.isArray(value);
    default:
      return typeof value === 'string' || typeof value === 'number';
  }
}
