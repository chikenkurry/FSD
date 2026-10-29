import {
  ArrayMaxSize,
  ArrayMinSize,
  ArrayUnique,
  IsArray,
  IsInt,
  IsUUID,
  IsOptional,
  IsString,
  IsIn,
  Matches,
  Max,
  Min,
  ValidateNested,
} from 'class-validator';
import { Type } from 'class-transformer';
import { QuestionDefinitionDto } from '../responses/question-answer';

/** Body of Planning's idempotent "provision round" command (P02). */
export class ProvisionRoundDto {
  @IsOptional()
  @IsIn(['publication', 'close'])
  rosterPolicy?: 'publication' | 'close';
  /** Idempotency key. Retries reuse it; reusing it with a different payload is rejected. */
  @IsUUID('all')
  operationId!: string;

  @IsUUID('all')
  roundId!: string;

  @IsUUID('all')
  planId!: string;

  @IsInt()
  @Min(1)
  optionRevision!: number;

  /** Activities members may answer in this round (2-8 in the MVP; 1 allowed for tests). */
  @IsArray()
  @ArrayMinSize(1)
  @ArrayMaxSize(8)
  @ArrayUnique()
  @IsUUID('all', { each: true })
  activityIds!: string[];

  @IsOptional()
  @IsUUID('all')
  optionSnapshotId?: string;

  @IsOptional()
  @IsArray()
  @ArrayMinSize(1)
  @ArrayMaxSize(30)
  @ArrayUnique()
  @IsUUID('all', { each: true })
  memberIds?: string[];

  @IsOptional()
  @IsArray()
  @ArrayMaxSize(100)
  @ValidateNested({ each: true })
  @Type(() => QuestionDefinitionDto)
  questions?: QuestionDefinitionDto[];

  @IsOptional()
  @IsString()
  @Matches(/^[A-Z]{3}$/)
  currency?: string;

  @IsOptional()
  @IsInt()
  @Min(0)
  @Max(9)
  minorDigits?: number;
}
