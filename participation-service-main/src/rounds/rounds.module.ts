import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module';
import { InternalRoundsController } from './internal-rounds.controller';
import { RoundsService } from './rounds.service';

@Module({
  imports: [AuthModule],
  controllers: [InternalRoundsController],
  providers: [RoundsService],
})
export class RoundsModule {}
