import { ArgumentsHost, Catch, ExceptionFilter, HttpException, Logger } from '@nestjs/common';
import type { Request, Response } from 'express';
import { ApiErrorCode, ApiErrorV1, ApiException } from './api-exception';
import { RequestWithId } from './request-id.middleware';

const GENERIC_BY_STATUS: Record<number, { code: ApiErrorCode; message: string }> = {
  400: { code: 'INVALID_INPUT', message: 'The request could not be understood' },
  401: { code: 'UNAUTHENTICATED', message: 'Authentication required' },
  403: { code: 'FORBIDDEN', message: 'You do not have access to this resource' },
  404: { code: 'NOT_FOUND', message: 'Resource not found' },
  409: { code: 'OPERATION_CONFLICT', message: 'The request conflicts with current state' },
  413: { code: 'INVALID_INPUT', message: 'Request body is too large' },
  429: { code: 'RATE_LIMITED', message: 'Too many requests' },
};

export function toApiError(
  exception: unknown,
  requestId: string,
): { status: number; body: ApiErrorV1; unexpected: boolean } {
  if (exception instanceof ApiException) {
    return {
      status: exception.getStatus(),
      unexpected: false,
      body: {
        code: exception.code,
        message: exception.message,
        retryable: exception.retryable,
        requestId,
        ...(exception.fieldErrors ? { fieldErrors: exception.fieldErrors } : {}),
      },
    };
  }

  // Other Nest HttpExceptions (unknown route, ...) and http-errors thrown by body-parser.
  const status =
    exception instanceof HttpException
      ? exception.getStatus()
      : typeof (exception as { status?: unknown })?.status === 'number'
        ? (exception as { status: number }).status
        : 500;

  if (status >= 400 && status < 500) {
    const generic = GENERIC_BY_STATUS[status] ?? GENERIC_BY_STATUS[400];
    return {
      status,
      unexpected: false,
      body: { ...generic, retryable: false, requestId },
    };
  }

  return {
    status: 500,
    unexpected: true,
    body: {
      code: 'INTERNAL',
      message: 'Something went wrong on our side',
      retryable: true,
      requestId,
    },
  };
}

@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
  private readonly logger = new Logger(AllExceptionsFilter.name);

  catch(exception: unknown, host: ArgumentsHost): void {
    const http = host.switchToHttp();
    const req = http.getRequest<Request & Partial<RequestWithId>>();
    const res = http.getResponse<Response>();
    const requestId = req.requestId ?? 'unknown';

    const { status, body, unexpected } = toApiError(exception, requestId);

    if (unexpected) {
      // Log the error and request id only. Never log request bodies: they hold private responses.
      const err = exception instanceof Error ? exception : new Error(String(exception));
      this.logger.error(`[${requestId}] ${req.method} ${req.path}: ${err.message}`, err.stack);
    }

    res.status(status).json(body);
  }
}
