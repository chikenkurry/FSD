import { randomUUID } from 'node:crypto';
import type { NextFunction, Request, Response } from 'express';

export interface RequestWithId extends Request {
  requestId: string;
}

const SAFE_ID = /^[A-Za-z0-9_-]{8,64}$/;

/** Reuses a well-formed incoming x-request-id (gateway/other services) or generates one. */
export function requestIdMiddleware(req: Request, res: Response, next: NextFunction): void {
  const incoming = req.header('x-request-id');
  const requestId = incoming && SAFE_ID.test(incoming) ? incoming : randomUUID();
  (req as RequestWithId).requestId = requestId;
  res.setHeader('x-request-id', requestId);
  next();
}
