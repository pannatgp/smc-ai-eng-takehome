import type { ChatResponse, MessageOut } from './types'

export const API_BASE_URL = 'http://localhost:8000'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, body.detail ?? `Request failed (${res.status})`)
  }
  return res.json() as Promise<T>
}

export async function register(email: string, password: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  await handle(res)
}

export async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams()
  body.set('username', email)
  body.set('password', password)

  const res = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  const data = await handle<{ access_token: string }>(res)
  return data.access_token
}

export async function sendChatMessage(token: string, message: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
  })
  return handle<ChatResponse>(res)
}

export async function getChatHistory(token: string): Promise<MessageOut[]> {
  const res = await fetch(`${API_BASE_URL}/chat/history`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return handle<MessageOut[]>(res)
}
