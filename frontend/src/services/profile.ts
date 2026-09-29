import { api } from "./api";
import type { Profile } from "../types/profile";

export async function fetchProfile(): Promise<Profile> {
  const { data } = await api.get<Profile>("/profile");
  return data;
}

export async function saveProfile(profile: Profile): Promise<Profile> {
  const { data } = await api.put<Profile>("/profile", profile);
  return data;
}
