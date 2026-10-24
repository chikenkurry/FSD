import { Body, Controller, Get, Param, Put, UseGuards } from '@nestjs/common';
import { IsIn, IsInt, Min } from 'class-validator';
import { CurrentMember, MemberSessionGuard } from '../auth/member-session.guard';
import { AuthorisedMember } from '../auth/session-authoriser';
import { RsvpsService } from './rsvps.service';

export class SaveRsvpDto {
  @IsInt() @Min(1) selectionVersion!: number;
  @IsInt() @Min(0) expectedRevision!: number;
  @IsIn(['GOING', 'MAYBE', 'DECLINED']) status!: string;
}

@Controller('rounds/:roundId/my-rsvp')
@UseGuards(MemberSessionGuard)
export class RsvpsController {
  constructor(private readonly rsvps: RsvpsService) {}
  @Get()
  get(@Param('roundId') roundId: string, @CurrentMember() member: AuthorisedMember) {
    return this.rsvps.get(roundId, member);
  }
  @Put()
  save(@Param('roundId') roundId: string, @CurrentMember() member: AuthorisedMember, @Body() body: SaveRsvpDto) {
    return this.rsvps.save(roundId, member, body);
  }
}
