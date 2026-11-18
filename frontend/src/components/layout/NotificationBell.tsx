import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { useI18n, type MessageKey } from "../../i18n";
import { formatWhen } from "../../lib/format";
import { getNotifications, markNotificationRead } from "../../lib/notifications";
import type { NotificationEvent, NotificationItem } from "../../lib/types";
import { Icon } from "../ui/Icon";
import "../../styles/notifications.css";

const EVENT_LABELS: Record<NotificationEvent, MessageKey> = {
  scan_ready: "notifications.scanReady",
  scan_failed: "notifications.scanFailed",
  analysis_ready: "notifications.analysisReady",
  analysis_failed: "notifications.analysisFailed",
};

const POLL_INTERVAL_MS = 30_000;

function targetFor(notification: NotificationItem): string | null {
  if (notification.scan_id !== null && notification.patient_id !== null) {
    const params = new URLSearchParams({
      patient: String(notification.patient_id),
      scan: String(notification.scan_id),
    });
    return `/scan?${params}`;
  }
  if (notification.analysis_run_id !== null) return `/analysis/${notification.analysis_run_id}`;
  return null;
}

export function NotificationBell() {
  const { user } = useAuth();
  const { t, lang } = useI18n();
  const navigate = useNavigate();
  const centerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getNotifications();
      setNotifications(result.results);
      setUnreadCount(result.unread_count);
      setError(null);
    } catch {
      setError("notifications.error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user?.role !== "doctor" && user?.role !== "pharmacist") return;
    void load();
    const interval = window.setInterval(() => void load(), POLL_INTERVAL_MS);
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
    };
  }, [load, user?.role]);

  useEffect(() => {
    if (!open) return;
    function onDown(event: MouseEvent) {
      if (centerRef.current && !centerRef.current.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (user?.role !== "doctor" && user?.role !== "pharmacist") return null;

  async function openNotification(notification: NotificationItem) {
    const target = targetFor(notification);
    if (!target) {
      setError("notifications.actionError");
      return;
    }
    try {
      const updated = await markNotificationRead(notification.id);
      setNotifications((current) => current.map((item) => item.id === updated.id ? updated : item));
      if (notification.read_at === null) setUnreadCount((count) => Math.max(0, count - 1));
      setError(null);
      setOpen(false);
      navigate(target);
    } catch {
      setError("notifications.actionError");
    }
  }

  const locale = lang === "bn" ? "bn-BD" : "en-GB";
  const unreadLabel = unreadCount > 99 ? "99+" : new Intl.NumberFormat(locale).format(unreadCount);

  return (
    <div className="notification-center" ref={centerRef}>
      <button
        type="button"
        className="icon-btn notification-trigger"
        aria-label={unreadCount > 0
          ? `${t("shell.notifications")}: ${t("notifications.unreadCount", { count: unreadLabel })}`
          : t("shell.notifications")}
        aria-expanded={open}
        aria-controls="notification-panel"
        onClick={() => {
          setOpen((value) => !value);
          if (!open) void load();
        }}
      >
        <Icon name="bell" />
        {unreadCount > 0 && <span className="notification-badge">{unreadLabel}</span>}
      </button>

      {open && (
        <section
          id="notification-panel"
          className="notification-panel"
          aria-label={t("notifications.title")}
          aria-busy={loading}
        >
          <h2>{t("notifications.title")}</h2>
          {error && (
            <p className="alert notification-error" role="alert">
              {t(error)}{" "}
              <button type="button" className="link-btn" onClick={() => void load()}>{t("common.retry")}</button>
            </p>
          )}
          {loading && notifications.length === 0 && <p className="muted" role="status">{t("common.loading")}</p>}
          {!loading && notifications.length === 0 && !error && (
            <p className="muted notification-empty">{t("notifications.empty")}</p>
          )}
          {notifications.length > 0 && (
            <ul className="notification-list">
              {notifications.map((notification) => (
                <li key={notification.id}>
                  <button
                    type="button"
                    className={`notification-item${notification.read_at === null ? " is-unread" : ""}`}
                    onClick={() => void openNotification(notification)}
                  >
                    <span className="notification-item-copy">
                      <strong>{t(EVENT_LABELS[notification.event])}</strong>
                      <time className="muted small" dateTime={notification.created_at}>
                        {formatWhen(notification.created_at, lang)}
                      </time>
                    </span>
                    {notification.read_at === null && <span className="notification-unread-dot" aria-hidden="true" />}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
