import { INestApplication, ValidationPipe } from '@nestjs/common';
import { AllExceptionsFilter } from './common/all-exceptions.filter';
import { requestIdMiddleware } from './common/request-id.middleware';
import { validationExceptionFactory } from './common/validation';

/** Shared by main.ts and the e2e tests so both run with identical pipes, filters and middleware. */
export function configureApp(app: INestApplication): void {
  app.use(requestIdMiddleware);
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      forbidNonWhitelisted: true,
      transform: true,
      exceptionFactory: validationExceptionFactory,
    }),
  );
  app.useGlobalFilters(new AllExceptionsFilter());
}
