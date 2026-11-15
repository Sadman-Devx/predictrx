import "../../styles/scan.css";
import { useScanImage } from "../../hooks/useScanImage";
import { useI18n } from "../../i18n";

/**
 * The stored prescription image, shown next to the medicine list on the Review screen so the person can check every row
 * against the original. It is fetched with the login token (no public URL exists) and every view is audited by the server.
 */
export function ScanImage({ scanId }: { scanId: number }) {
  const { t } = useI18n();
  const { state, retry } = useScanImage(scanId);

  return (
    <div className={`image-slot${state.status === "ready" ? " has-image" : ""}`}>
      {state.status === "loading" && <p className="muted small" role="status">{t("review.image.loading")}</p>}

      {state.status === "gone" && <p className="muted small">{t("review.image.gone")}</p>}

      {state.status === "error" && (
        <p className="alert" role="alert">
          {t("review.image.error")}{" "}
          <button type="button" className="link-btn" onClick={retry}>{t("common.retry")}</button>
        </p>
      )}

      {state.status === "ready" && (
        <div className="image-view">
          <img src={state.url} alt={t("review.image.alt")} />
          <p className="small">
            <a href={state.url} target="_blank" rel="noreferrer">{t("review.image.open")}</a>
          </p>
        </div>
      )}
    </div>
  );
}