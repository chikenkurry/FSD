import { BadRequestException, NotFoundException } from '@nestjs/common';
import { toApiError } from './all-exceptions.filter';
import { Errors } from './api-exception';

const REQUEST_ID = 'req-12345678';

describe('toApiError', () => {
  it('maps an ApiException to the ApiErrorV1 shape', () => {
    const { status, body, unexpected } = toApiError(
      Errors.invalidInput([{ field: 'budget.capMinor', message: 'required' }]),
      REQUEST_ID,
    );
    expect(status).toBe(400);
    expect(unexpected).toBe(false);
    expect(body).toEqual({
      code: 'INVALID_INPUT',
      message: 'Request validation failed',
      retryable: false,
      requestId: REQUEST_ID,
      fieldErrors: [{ field: 'budget.capMinor', message: 'required' }],
    });
  });

  it('marks upstream failures as retryable', () => {
    const { status, body } = toApiError(Errors.upstreamUnavailable(), REQUEST_ID);
    expect(status).toBe(503);
    expect(body).toMatchObject({ code: 'UPSTREAM_UNAVAILABLE', retryable: true });
  });

  it('gives other Nest HTTP exceptions a safe generic body', () => {
    const notFound = toApiError(new NotFoundException('Cannot GET /secret/path'), REQUEST_ID);
    expect(notFound.status).toBe(404);
    expect(notFound.body.code).toBe('NOT_FOUND');
    expect(JSON.stringify(notFound.body)).not.toContain('secret');

    expect(toApiError(new BadRequestException('x'), REQUEST_ID).body.code).toBe('INVALID_INPUT');
  });

  it('handles http-errors from body parsing, such as an oversized body', () => {
    const tooLarge = Object.assign(new Error('request entity too large'), { status: 413 });
    const { status, body } = toApiError(tooLarge, REQUEST_ID);
    expect(status).toBe(413);
    expect(body.code).toBe('INVALID_INPUT');
  });

  it('hides the details of unexpected errors and flags them for logging', () => {
    const { status, body, unexpected } = toApiError(new Error('connection string leaked'), REQUEST_ID);
    expect(status).toBe(500);
    expect(unexpected).toBe(true);
    expect(body).toEqual({
      code: 'INTERNAL',
      message: 'Something went wrong on our side',
      retryable: true,
      requestId: REQUEST_ID,
    });
  });
});
