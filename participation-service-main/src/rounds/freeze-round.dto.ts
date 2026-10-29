import {
  ArrayMaxSize,
  ArrayMinSize,
  ArrayUnique,
  IsArray,
  IsUUID,
  IsOptional,
  IsInt,
  Min,
  IsBoolean,
} from 'class-validator';

/** Body of Planning's idempotent "freeze round" command. */
export class FreezeRoundDto {
  @IsOptional()
  @IsBoolean()
  requireComplete?: boolean;
  /**
   * Early close: freeze with whoever has submitted. Members without a complete,
   * current response stay on the roster but are not counted in the decision.
   */
  @IsOptional()
  @IsBoolean()
  countRespondedOnly?: boolean;
  @IsOptional()
  @IsUUID('all')
  optionSnapshotId?: string;

  @IsOptional()
  @IsInt()
  @Min(1)
  optionRevision?: number;
  /** Idempotency key. Retries reuse it; reusing it with a different roster is rejected. */
  @IsUUID('all')
  operationId!: string;

  @IsUUID('all')
  roundId!: string;

  /**
   * Approved roster for this round. Use the same member IDs Planning returns from session
   * authorisation (`user_id` on plan members). Missing members are recorded as incomplete.
   */
  @IsArray()
  @ArrayMinSize(1)
  @ArrayMaxSize(30)
  @ArrayUnique()
  @IsUUID('all', { each: true })
  memberIds!: string[];
}
