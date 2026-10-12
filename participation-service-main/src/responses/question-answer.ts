import { Allow, ArrayMaxSize, IsArray, IsBoolean, IsDefined, IsIn, IsOptional, IsUUID } from 'class-validator';

export class QuestionDefinitionDto {
  @IsUUID('all')
  questionId!: string;

  @IsBoolean()
  required!: boolean;

  @IsIn(['text', 'choice', 'multi_choice', 'number', 'boolean', 'date_intervals'])
  answerFormat!: string;

  @IsOptional()
  @IsArray()
  @ArrayMaxSize(100)
  choices?: unknown[];
}

export class QuestionAnswerDto {
  @IsUUID('all')
  question_id!: string;

  @IsDefined()
  value!: unknown;

  // Meaning is checked by preprocessing; Participation retains the exact review record.
  @Allow()
  confirmed_requirement?: unknown;

  @Allow()
  confirmed_requirements?: unknown;
}
