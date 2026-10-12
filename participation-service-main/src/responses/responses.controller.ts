import { Body, Controller, Get, HttpCode, Param, Post, Put, UseGuards } from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import { CurrentMember, MemberSessionGuard } from '../auth/member-session.guard';
import { AuthorisedMember } from '../auth/session-authoriser';
import { MyResponseView } from './my-response.view';
import { ResponsesService } from './responses.service';
import { SaveDraftDto } from './save-draft.dto';
import { SubmitResponseDto } from './submit-response.dto';

/**
 * A member only ever reaches their own response: the member comes from the session,
 * there is no memberId in the URL or body to tamper with. (MemberSessionGuard validates :roundId.)
 */
@ApiTags('member response')
@ApiBearerAuth()
@Controller('rounds/:roundId/my-response')
@UseGuards(MemberSessionGuard)
export class ResponsesController {
  constructor(private readonly responses: ResponsesService) {}

  @Get()
  @ApiOperation({
    summary: "Read the caller's own draft",
    description: 'Returns an empty draft with revision 0 if the member has never saved.',
  })
  get(
    @Param('roundId') roundId: string,
    @CurrentMember() member: AuthorisedMember,
  ): Promise<MyResponseView> {
    return this.responses.getOwn(roundId, member);
  }

  @Put()
  @ApiOperation({
    summary: "Replace the caller's own draft",
    description:
      'Send the revision you loaded as expectedRevision. 409 STALE_VERSION if it changed, 409 ROUND_CLOSED once frozen.',
  })
  save(
    @Param('roundId') roundId: string,
    @CurrentMember() member: AuthorisedMember,
    @Body() dto: SaveDraftDto,
  ): Promise<MyResponseView> {
    return this.responses.saveDraft(roundId, member, dto);
  }

  @Post('submit')
  @HttpCode(200)
  @ApiOperation({
    summary: "Submit the caller's own response",
    description:
      'Requires a complete draft: budget answered and every activity answered. 409 ROUND_CLOSED once frozen.',
  })
  submit(
    @Param('roundId') roundId: string,
    @CurrentMember() member: AuthorisedMember,
    @Body() dto: SubmitResponseDto,
  ): Promise<MyResponseView> {
    return this.responses.submit(roundId, member, dto);
  }
}
