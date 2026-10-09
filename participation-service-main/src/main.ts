import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { NestExpressApplication } from '@nestjs/platform-express';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { AppModule } from './app.module';
import { AppConfig } from './config/app-config';
import { configureApp } from './configure-app';

async function bootstrap(): Promise<void> {
  const app = await NestFactory.create<NestExpressApplication>(AppModule);
  app.disable('x-powered-by');
  app.useBodyParser('json', { limit: '100kb' });
  configureApp(app);

  const openApi = SwaggerModule.createDocument(
    app,
    new DocumentBuilder()
      .setTitle('What2Do Participation Service')
      .setDescription('Member responses, private budgets, snapshots and RSVPs')
      .setVersion('0.1.0')
      .addBearerAuth()
      .build(),
  );
  SwaggerModule.setup('docs', app, openApi);

  app.enableShutdownHooks();
  await app.listen(app.get(AppConfig).port);
}

void bootstrap();
