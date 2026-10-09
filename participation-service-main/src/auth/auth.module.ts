import { Module } from '@nestjs/common';
import { AppConfig } from '../config/app-config';
import { RoundRepository } from '../rounds/round.repository';
import { DevSessionAuthoriser } from './dev-session-authoriser';
import { InternalTokenGuard } from './internal-token.guard';
import { MemberSessionGuard } from './member-session.guard';
import { PlanningSessionAuthoriser } from './planning-session-authoriser';
import { SessionAuthoriser } from './session-authoriser';

@Module({
  providers: [
    {
      provide: SessionAuthoriser,
      inject: [AppConfig, RoundRepository],
      useFactory: (config: AppConfig, rounds: RoundRepository): SessionAuthoriser =>
        config.authMode === 'dev'
          ? new DevSessionAuthoriser(rounds)
          : new PlanningSessionAuthoriser(config),
    },
    MemberSessionGuard,
    InternalTokenGuard,
  ],
  exports: [SessionAuthoriser, MemberSessionGuard, InternalTokenGuard],
})
export class AuthModule {}
