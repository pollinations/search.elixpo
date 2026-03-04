const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:9002';
const INTERNAL_KEY = process.env.INTERNAL_API_KEY || '';

export function backendHeaders(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'X-Internal-Key': INTERNAL_KEY,
  };
}

export function backendUrl(path: string): string {
  return `${BACKEND_URL}${path}`;
}
