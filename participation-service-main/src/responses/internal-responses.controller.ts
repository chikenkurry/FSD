import { Controller, Get, Param, UseGuards } from '@nestjs/common';
import { InternalTokenGuard } from '../auth/internal-token.guard';
import { Errors } from '../common/api-exception';
import { isUuid } from '../common/validation';
import { ResponsesService } from './responses.service';

@Controller('internal/rounds/:roundId/members/:memberId')
@UseGuards(InternalTokenGuard)
export class InternalResponsesController {
  constructor(private readonly responses: ResponsesService) {}

  @Get('preview-snapshot')
  preview(@Param('roundId') roundId: string, @Param('memberId') memberId: string) {
    if (!isUuid(roundId) || !isUuid(memberId)) throw Errors.invalidInput([{ field: 'id', message: 'UUID required' }]);
    return this.responses.previewSnapshot(roundId, memberId);
  }
}
