import { ValidationError } from 'class-validator';
import { Errors, FieldError } from './api-exception';

function flattenValidationErrors(errors: ValidationError[], parent = ''): FieldError[] {
  return errors.flatMap((error) => {
    const field = parent ? `${parent}.${error.property}` : error.property;
    const own = Object.values(error.constraints ?? {}).map((message) => ({ field, message }));
    return [...own, ...flattenValidationErrors(error.children ?? [], field)];
  });
}

export function validationExceptionFactory(errors: ValidationError[]) {
  return Errors.invalidInput(flattenValidationErrors(errors));
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: unknown): value is string {
  return typeof value === 'string' && UUID.test(value);
}

/** Fails with 400 INVALID_INPUT naming `field` unless `value` is a UUID. */
export function assertUuid(value: unknown, field: string): asserts value is string {
  if (!isUuid(value)) {
    throw Errors.invalidInput([{ field, message: `${field} must be a UUID` }]);
  }
}