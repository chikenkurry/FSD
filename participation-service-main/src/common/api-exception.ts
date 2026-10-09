import { HttpException } from '@nestjs/common';

/**
 * Local mirror of the shared ApiErrorV1 contract (owned by F02 in the team's contract set).
 * Align the codes below with the agreed contract once it is published.
 */
export type ApiErrorCode =
  | 'UNAUTHENTICATED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'INVALID_INPUT'
  | 'STALE_VERSION'
  | 'ROUND_CLOSED'
  | 'OPERATION_CONFLICT'
  | 'RATE_LIMITED'
  | 'UPSTREAM_UNAVAILABLE'
  | 'INTERNAL';

export interface FieldError {
  field: string;
  message: string;
}

export interface ApiErrorV1 {
  code: ApiErrorCode;
  message: string;
  retryable: boolean;
  requestId: string;
  fieldErrors?: FieldError[];
}

export class ApiException extends HttpException {
  constructor(
    status: number,
    readonly code: ApiErrorCode,
    message: string,
    readonly retryable = false,
    readonly fieldErrors?: FieldError[],
  ) {
    super({ code, message }, status);
  }
}

export const Errors = {
  unauthenticated: (message = 'Authentication required') =>
    new ApiException(401, 'UNAUTHENTICATED', message),
  forbidden: (message = 'You do not have access to this resource') =>
    new ApiException(403, 'FORBIDDEN', message),
  notFound: (message = 'Resource not found') => new ApiException(404, 'NOT_FOUND', message),
  invalidInput: (fieldErrors: FieldError[], message = 'Request validation failed') =>
    new ApiException(400, 'INVALID_INPUT', message, false, fieldErrors),
  staleVersion: (message = 'The resource changed since you last loaded it') =>
    new ApiException(409, 'STALE_VERSION', message),
  roundClosed: (message = 'This round is no longer accepting responses') =>
    new ApiException(409, 'ROUND_CLOSED', message),
  operationConflict: (message: string) => new ApiException(409, 'OPERATION_CONFLICT', message),
  upstreamUnavailable: (message = 'A required service is unavailable, please retry') =>
    new ApiException(503, 'UPSTREAM_UNAVAILABLE', message, true),
};
