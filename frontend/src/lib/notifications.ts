import { api } from "./api";
import type { NotificationList, NotificationItem } from "./types";

/** GET /api/notifications/ — the latest ten events and the signed-in clinician's unread count. */
export const getNotifications = () => api<NotificationList>("/notifications/");

/** POST /api/notifications/{id}/read/ — idempotently mark one event as read. */
export const markNotificationRead = (id: number) =>
  api<NotificationItem>(`/notifications/${id}/read/`, { method: "POST", body: JSON.stringify({}) });
