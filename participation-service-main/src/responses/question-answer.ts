import {
  Allow,
  ArrayMaxSize,
  IsArray,
  IsBoolean,
  IsDefined,
  IsIn,
  IsOptional,
  IsUUID,
  IsInt,
  Min,
} from 'class-validator';

export class QuestionDefinitionDto {
  @IsUUID('all')
  questionId!: string;

  @IsBoolean()
  required!: boolean;

  @IsIn(['text', 'choice', 'multi_choice', 'number', 'boolean', 'date_intervals', 'option_rating', 'date_poll'])
  answerFormat!: string;

  @IsOptional()
  @IsArray()
  @ArrayMaxSize(100)
  choices?: unknown[];
}

export class QuestionAnswerDto {
  @IsOptional()
  @IsInt()
  @Min(1)
  reviewed_revision?: number;
  @IsUUID('all')
  question_id!: string;

  @IsDefined()
  value!: unknown;

  /** How much this answer matters to the member; scales their own weight for it. */
  @IsOptional()
  @IsIn(['low', 'normal', 'high'])
  importance?: 'low' | 'normal' | 'high';

  // Meaning is checked by preprocessing; Participation retains the exact review record.
  @Allow()
  confirmed_requirement?: unknown;

  @Allow()
  confirmed_requirements?: unknown;
}
