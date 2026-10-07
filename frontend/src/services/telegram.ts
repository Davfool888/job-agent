import { api } from "./api";

export interface TelegramStatus {
  connected: boolean;
  username: string | null;
  linked_at: string | null;
  valid: boolean;
  error?: string;
  bot_username: string | null;
}

export interface TelegramLinkStart {
  code: string;
  deep_link: string;
  bot_username: string;
  expires_in_minutes: number;
}

export async function fetchTelegramStatus(): Promise<TelegramStatus> {
  const { data } = await api.get<TelegramStatus>("/telegram/status");
  return data;
}

export async function startTelegramLink(): Promise<TelegramLinkStart> {
  const { data } = await api.post<TelegramLinkStart>("/telegram/link/start");
  return data;
}

export async function testTelegram(): Promise<{ message_id: number | null }> {
  const { data } = await api.post("/telegram/test");
  return data;
}

export async function unlinkTelegram(): Promise<void> {
  await api.delete("/telegram");
}
