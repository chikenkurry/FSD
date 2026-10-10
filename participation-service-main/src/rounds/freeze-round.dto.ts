import { ArrayMaxSize, ArrayMinSize, ArrayUnique, IsArray, IsUUID } from 'class-validator';

/** Body of Planning's idempotent "freeze round" command. */
export class FreezeRoundDto {
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
