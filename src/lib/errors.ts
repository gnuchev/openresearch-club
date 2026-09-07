export interface FieldError {
  field?: string;
  message: string;
}

export class HttpError extends Error {
  constructor(
    public status: number,
    public title: string,
    public detail?: string,
    public errors?: FieldError[],
    public headers: Record<string, string> = {},
  ) {
    super(detail ?? title);
  }
}

export const badRequest = (detail: string, errors?: FieldError[]) => new HttpError(400, 'Bad Request', detail, errors);
export const unauthorized = (detail = 'Missing or invalid token') => new HttpError(401, 'Unauthorized', detail);
export const forbidden = (detail: string) => new HttpError(403, 'Forbidden', detail);
export const notFound = (what = 'Not found') => new HttpError(404, 'Not Found', what);
export const conflict = (detail: string, headers?: Record<string, string>) => new HttpError(409, 'Conflict', detail, undefined, headers);
export const gone = (detail: string) => new HttpError(410, 'Gone', detail);
export const tooLarge = (detail: string) => new HttpError(413, 'Payload Too Large', detail);
export const unprocessable = (detail: string) => new HttpError(422, 'Unprocessable Content', detail);
export const tooMany = (detail: string, retryAfterSeconds: number) =>
  new HttpError(429, 'Too Many Requests', detail, undefined, { 'Retry-After': String(retryAfterSeconds) });

export function problemResponse(err: HttpError, instance?: string): Response {
  const body: Record<string, unknown> = { type: 'about:blank', title: err.title, status: err.status };
  if (err.detail) body.detail = err.detail;
  if (instance) body.instance = instance;
  if (err.errors && err.errors.length) body.errors = err.errors;
  return new Response(JSON.stringify(body), {
    status: err.status,
    headers: { 'content-type': 'application/problem+json', ...err.headers },
  });
}
