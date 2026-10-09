import { Module } from '@nestjs/common';
import { AuthModule } from './auth/auth.module';
import { ConfigModule } from './config/config.module';
import { HealthModule } from './health/health.module';
import { PrismaModule } from './prisma/prisma.module';
import { ResponsesModule } from './responses/responses.module';
import { RoundsModule } from './rounds/rounds.module';

@Module({
  imports: [ConfigModule, PrismaModule, AuthModule, HealthModule, RoundsModule, ResponsesModule],
})
export class AppModule {}
