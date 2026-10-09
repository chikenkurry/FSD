import { ArrayMaxSize, ArrayMinSize, ArrayUnique, IsArray, IsInt, IsUUID, Min } from 'class-validator';

/** Body of Planning's idempotent "provision round" command (P02). */
export class ProvisionRoundDto {
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
}
