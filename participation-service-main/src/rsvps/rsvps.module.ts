import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module';
import { RsvpsController } from './rsvps.controller';
import { RsvpsService } from './rsvps.service';

@Module({ imports: [AuthModule], controllers: [RsvpsController], providers: [RsvpsService] })
export class RsvpsModule {}
