import { createHash, timingSafeEqual } from 'node:crypto';
import { CanActivate, ExecutionContext, Injectable } from '@nestjs/common';
import type { Request } from 'express';
import { Errors } from '../common/api-exception';
import { AppConfig } from '../config/app-config';

function digest(value: string): Buffer {
  return createHash('sha256').update(value).digest();
}

/**
 * Protects /internal/* routes with a shared service secret. These routes must also be
 * excluded from the public gateway; this guard is the second line of defence.
 */
@Injectable()
export class InternalTokenGuard implements CanActivate {
  constructor(private readonly config: AppConfig) {}

  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest<Request>();
    const provided = req.header('x-internal-token');
    if (!provided) throw Errors.unauthenticated('Internal credential required');
    // Hash both sides so the comparison is constant-time and length-independent.
    if (!timingSafeEqual(digest(provided), digest(this.config.internalApiToken))) {
      throw Errors.forbidden('Invalid internal credential');
    }
    return true;
  }
}
