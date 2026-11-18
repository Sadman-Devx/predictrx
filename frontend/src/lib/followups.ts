import { api } from "./api";
import type { FollowUpTask, FollowUpTaskCreate, FollowUpTaskUpdate, Paginated } from "./types";

export const listFollowUps = (page = 1) =>
  api<Paginated<FollowUpTask>>(`/follow-ups/?page=${page}&page_size=100`);

export const createFollowUp = (data: FollowUpTaskCreate) =>
  api<FollowUpTask>("/follow-ups/", { method: "POST", body: JSON.stringify(data) });

export const updateFollowUp = (id: number, data: FollowUpTaskUpdate) =>
  api<FollowUpTask>(`/follow-ups/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
