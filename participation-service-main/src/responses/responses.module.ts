import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module';
import { ResponsesController } from './responses.controller';
import { ResponsesService } from './responses.service';

@Module({
  imports: [AuthModule],
  controllers: [ResponsesController],
  providers: [ResponsesService],
})
export class ResponsesModule {}
