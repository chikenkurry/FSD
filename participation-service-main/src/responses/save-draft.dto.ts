import { Type } from 'class-transformer';
import {
  ArrayMaxSize,
  IsArray,
  IsIn,
  IsInt,
  IsISO8601,
  IsOptional,
  IsString,
  IsUUID,
  Matches,
  Max,
  MaxLength,
  Min,
  ValidateNested,
} from 'class-validator';
import { ANSWER_KINDS, AnswerKindValue, BUDGET_KINDS, BudgetKindValue } from './response.types';

export const MAX_INTERVALS = 500;
export const MAX_ACTIVITIES = 8;
/** SGD minor units. 100,000,000 = S$1,000,000.00, far above any sensible per-person cap. */
export const MAX_BUDGET_MINOR = 100_000_000;
/** Must carry an explicit offset so an instant is never guessed from server time. */
const HAS_OFFSET = /(Z|[+-]\d{2}:\d{2})$/;

export class AvailabilityIntervalDto {
  @IsISO8601({ strict: true })
  @Matches(HAS_OFFSET, { message: 'startAt must include a timezone offset such as Z or +08:00' })
  startAt!: string;

  @IsISO8601({ strict: true })
  @Matches(HAS_OFFSET, { message: 'endAt must include a timezone offset such as Z or +08:00' })
  endAt!: string;
}

export class BudgetDto {
  /** UNANSWERED is neither zero nor unlimited. UNLIMITED is the explicit "no spending limit". */
  @IsIn(BUDGET_KINDS)
  kind!: BudgetKindValue;

  /** Per-person cap in minor units (cents). Required when kind = CAP, forbidden otherwise. */
  @IsOptional()
  @IsInt()
  @Min(0)
  @Max(MAX_BUDGET_MINOR)
  capMinor?: number;
}

export class ActivityAnswerDto {
  @IsUUID('all')
  activityId!: string;

  @IsIn(ANSWER_KINDS)
  kind!: AnswerKindValue;

  /** 0 strongly dislike ... 4 love. Required when kind = RATING, forbidden otherwise. */
  @IsOptional()
  @IsInt()
  @Min(0)
  @Max(4)
  rating?: number;
}

/** Full replacement of the caller's draft. Partial drafts are allowed; submission (R02) checks completeness. */
export class SaveDraftDto {
  /** Revision the client last loaded (0 if it has never saved). Mismatch -> 409 STALE_VERSION. */
  @IsInt()
  @Min(0)
  expectedRevision!: number;

  /** Option revision the form was rendered from. Must equal the round's current revision. */
  @IsInt()
  @Min(1)
  acknowledgedOptionRevision!: number;

  @IsArray()
  @ArrayMaxSize(MAX_INTERVALS)
  @ValidateNested({ each: true })
  @Type(() => AvailabilityIntervalDto)
  availability!: AvailabilityIntervalDto[];

  @ValidateNested()
  @Type(() => BudgetDto)
  budget!: BudgetDto;

  @IsArray()
  @ArrayMaxSize(MAX_ACTIVITIES)
  @ValidateNested({ each: true })
  @Type(() => ActivityAnswerDto)
  activityAnswers!: ActivityAnswerDto[];

  /** Never used by the algorithm and never shared. */
  @IsOptional()
  @IsString()
  @MaxLength(1000)
  privateNote?: string | null;
}
