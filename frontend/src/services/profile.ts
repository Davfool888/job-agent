import { api } from "./api";
import type { Profile, RichProfile, TailorResult } from "../types/profile";

export async function fetchProfile(): Promise<Profile> {
  const { data } = await api.get<Profile>("/profile");
  return data;
}

export async function saveProfile(profile: Profile): Promise<Profile> {
  const { data } = await api.put<Profile>("/profile", profile);
  return data;
}

export async function fetchFullProfile(): Promise<RichProfile> {
  const { data } = await api.get<RichProfile>("/profile/full");
  return data;
}

export async function saveFullProfile(
  profile: Partial<RichProfile>,
): Promise<{ profile: RichProfile; warnings: string[] }> {
  const { data } = await api.put("/profile/full", profile);
  return data;
}

export async function tailorJob(jobId: number): Promise<TailorResult> {
  const { data } = await api.post<TailorResult>(`/jobs/${jobId}/tailor`);
  return data;
}
