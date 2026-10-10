import { Body, Controller, Get, HttpCode, Param, Post, UseGuards } from '@nestjs/common';
import { ApiHeader, ApiOperation, ApiTags } from '@nestjs/swagger';
import { InternalTokenGuard } from '../auth/internal-token.guard';
import { ResponseSnapshotV1 } from '../responses/decision-snapshot';
import { FreezeRoundDto } from './freeze-round.dto';
import { ProvisionRoundDto } from './provision-round.dto';
import { FreezeResult, ProgressResult, ProvisionResult, RoundsService } from './rounds.service';

/** Service-to-service only. Do NOT route /internal/* through the public gateway. */
@ApiTags('internal')
@ApiHeader({ name: 'x-internal-token', required: true, description: 'Shared service secret' })
@Controller('internal/rounds')
@UseGuards(InternalTokenGuard)
export class InternalRoundsController {
  constructor(private readonly rounds: RoundsService) {}

  @Post('provision')
  @HttpCode(200)
  @ApiOperation({
    summary: 'Provision a round (idempotent)',
    description:
      'Opens the round for responses. Retry with the same operationId and payload; a different payload for the same round or operationId is 409 OPERATION_CONFLICT.',
  })
  provision(@Body() dto: ProvisionRoundDto): Promise<ProvisionResult> {
    return this.rounds.provision(dto);
  }

  @Post('freeze')
  @HttpCode(200)
  @ApiOperation({
    summary: 'Freeze a round (idempotent)',
    description:
      'Called by Planning when closing collection. Retry with the same operationId and roster. Writes after this return 409 ROUND_CLOSED.',
  })
  freeze(@Body() dto: FreezeRoundDto): Promise<FreezeResult> {
    return this.rounds.freeze(dto);
  }

  @Get(':roundId/response-snapshot')
  @ApiOperation({
    summary: 'Read the immutable response snapshot',
    description:
      'For Decision. Snake_case fields match the algorithm input participants/constraints/preferences. Private notes are omitted.',
  })
  getSnapshot(@Param('roundId') roundId: string): Promise<ResponseSnapshotV1> {
    return this.rounds.getSnapshot(roundId);
  }

  @Get(':roundId/progress')
  @ApiOperation({
    summary: 'Response progress for a round',
    description: 'Counts and per-member status only. No budgets, availability, or notes.',
  })
  progress(@Param('roundId') roundId: string): Promise<ProgressResult> {
    return this.rounds.progress(roundId);
  }
}
