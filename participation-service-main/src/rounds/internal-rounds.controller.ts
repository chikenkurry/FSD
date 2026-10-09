import { Body, Controller, HttpCode, Post, UseGuards } from '@nestjs/common';
import { ApiHeader, ApiOperation, ApiTags } from '@nestjs/swagger';
import { InternalTokenGuard } from '../auth/internal-token.guard';
import { ProvisionRoundDto } from './provision-round.dto';
import { ProvisionResult, RoundsService } from './rounds.service';

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
}
