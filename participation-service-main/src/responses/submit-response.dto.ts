import { IsInt, Min } from 'class-validator';

export class SubmitResponseDto {
  /** Revision the client last loaded. Mismatch -> 409 STALE_VERSION. */
  @IsInt()
  @Min(0)
  expectedRevision!: number;
}
