import { api } from "./api";
import type {
  SchedulerStatus,
  SearchProfile,
  SearchProfileRun,
} from "../types/searchProfile";
import type { Job } from "../types/job";

export async function fetchSearchProfiles(): Promise<SearchProfile[]> {
  const { data } = await api.get<SearchProfile[]>("/search-profiles");
  return data;
}

export async function createSearchProfile(
  payload: Partial<SearchProfile>,
): Promise<SearchProfile> {
  const { data } = await api.post<SearchProfile>("/search-profiles", payload);
  return data;
}

export async function updateSearchProfile(
  id: string,
  payload: Partial<SearchProfile>,
): Promise<SearchProfile> {
  const { data } = await api.put<SearchProfile>(
    `/search-profiles/${id}`,
    payload,
  );
  return data;
}

export async function deleteSearchProfile(id: string): Promise<void> {
  await api.delete(`/search-profiles/${id}`);
}

export async function runSearchProfile(id: string): Promise<SearchProfileRun> {
  const { data } = await api.post<SearchProfileRun>(
    `/search-profiles/${id}/run`,
  );
  return data;
}

export async function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  const { data } = await api.get<SchedulerStatus>("/scheduler/status");
  return data;
}

export async function fetchJobsSince(
  sinceIso: string,
  limit = 200,
): Promise<Job[]> {
  const { data } = await api.get<Job[]>("/jobs", {
    params: { limit, since: sinceIso },
  });
  return data;
}
