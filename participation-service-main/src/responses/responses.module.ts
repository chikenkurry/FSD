import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module';
import { ResponsesController } from './responses.controller';
import { ResponsesService } from './responses.service';
import { InternalResponsesController } from './internal-responses.controller';

@Module({
  imports: [AuthModule],
  controllers: [ResponsesController, InternalResponsesController],
  providers: [ResponsesService],
})
export class ResponsesModule {}
