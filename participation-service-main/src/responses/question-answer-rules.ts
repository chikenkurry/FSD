import { FieldError } from '../common/api-exception';
import { IdSet, normaliseId } from '../common/ids';
import { QuestionAnswerDto, QuestionDefinitionDto } from './question-answer';

function validJson(value: unknown): boolean {
  try {
    const text = JSON.stringify(value);
    return text !== undefined && text.length <= 16_000;
  } catch {
    return false;
  }
}

export function answeredRequiredQuestions(answers: QuestionAnswerDto[], questions: QuestionDefinitionDto[]): boolean {
  const present = new IdSet(answers.filter((answer) => isAnswered(answer.value)).map((answer) => answer.question_id));
  return questions.every((q) => !q.required || present.has(q.questionId));
}

function isAnswered(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === 'string') return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value as object).length > 0;
  return true;
}

export function validateQuestionAnswers(
  answers: QuestionAnswerDto[],
  definitions: QuestionDefinitionDto[],
): FieldError[] {
  const errors: FieldError[] = [];
  const questions = new Map(definitions.map((q) => [normaliseId(q.questionId), q]));
  const answered = new IdSet();
  for (const [index, answer] of answers.entries()) {
    const definition = questions.get(normaliseId(answer.question_id));
    if (!definition || answered.has(answer.question_id) || !validJson(answer.value)) {
      errors.push({ field: `answers.${index}`, message: 'Unknown, duplicate or invalid question answer' });
      continue;
    }
    answered.add(answer.question_id);
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
  if (definition.answerFormat === 'date_poll') {
    // Each proposed date gets yes, maybe or no; only published dates can be answered.
    const dates = new Set((definition.choices ?? []).map((choice) => String(choice)));
    return Object.entries(value as Record<string, unknown>).every(
      ([day, answer]) => dates.has(day) && ['yes', 'maybe', 'no'].includes(answer as string),
    );
  }
  if (definition.answerFormat !== 'choice' && definition.answerFormat !== 'multi_choice') return true;
  const choices = (definition.choices ?? []).map((choice) =>
    typeof choice === 'object' && choice !== null ? (choice as { choice_id?: unknown }).choice_id : choice,
  );
  const selected = Array.isArray(value) ? value : [value];
  return selected.every((item) => choices.includes(item));
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
    case 'date_poll':
      return typeof value === 'object' && value !== null && !Array.isArray(value) && Object.keys(value).length <= 31;
    case 'option_rating':
      // Option ID -> whole-number rating from 0 (not for me) to 4 (love it).
      return (
        typeof value === 'object' &&
        value !== null &&
        !Array.isArray(value) &&
        Object.keys(value).length <= 20 &&
        Object.values(value).every(
          (rating) => Number.isInteger(rating) && (rating as number) >= 0 && (rating as number) <= 4,
        )
      );
    default:
      return typeof value === 'string' || typeof value === 'number';
  }
}
