import { Controller, Get } from '@nestjs/common';
import { Errors } from '../common/api-exception';
import { PrismaService } from '../prisma/prisma.service';

@Controller('health')
export class HealthController {
  constructor(private readonly prisma: PrismaService) {}

  /** Liveness: the process is up. */
  @Get()
  live(): { status: 'ok' } {
    return { status: 'ok' };
  }

  /** Readiness: the database answers. Use this for load balancer / orchestrator checks. */
  @Get('ready')
  async ready(): Promise<{ status: 'ok' }> {
    try {
      await this.prisma.$queryRaw`SELECT 1`;
      return { status: 'ok' };
    } catch {
      throw Errors.upstreamUnavailable('Database unavailable');
    }
  }
}
