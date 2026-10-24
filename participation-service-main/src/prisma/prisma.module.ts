import { Global, Module } from '@nestjs/common';
import { ResponseRepository } from '../responses/response.repository';
import { RoundRepository } from '../rounds/round.repository';
import { PrismaResponseRepository } from './prisma-response.repository';
import { PrismaRoundRepository } from './prisma-round.repository';
import { PrismaService } from './prisma.service';

/** The persistence adapter: binds the repository interfaces to their Prisma implementations. */
@Global()
@Module({
  providers: [
    PrismaService,
    { provide: RoundRepository, useClass: PrismaRoundRepository },
    { provide: ResponseRepository, useClass: PrismaResponseRepository },
  ],
  exports: [PrismaService, RoundRepository, ResponseRepository],
})
export class PrismaModule {}
