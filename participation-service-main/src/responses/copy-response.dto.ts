import { IsUUID } from 'class-validator';

export class CopyResponseDto {
  @IsUUID('all')
  sourceRoundId!: string;
}
