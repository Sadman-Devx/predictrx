import { Component, type ErrorInfo, type ReactNode } from "react";
import { useI18n } from "../../i18n";
import { StateBlock } from "./StateBlock";

function CrashFallback() {
  const { t } = useI18n();
  return (
    <StateBlock
      kind="error"
      title={t("crash.title")}
      action={
        <button type="button" className="btn" onClick={() => window.location.reload()}>
          {t("crash.reload")}
        </button>
      }
    >
      <p>{t("crash.text")}</p>
    </StateBlock>
  );
}

interface Props {
  children: ReactNode;
}
interface State {
  failed: boolean;
}

/**
 * Last line of defence: if a screen throws while drawing, the person sees a clear message and a reload button instead of a
 * blank page. Nothing that was being drawn is shown (a half-built result is never presented as a final one).
 * Place it with a `key` that changes on navigation so moving to another screen clears the error.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Log the kind of error and the component names only: never props or data, which can hold patient text.
    console.error("UI error:", error.name, info.componentStack ?? "");
  }

  render() {
    return this.state.failed ? <CrashFallback /> : this.props.children;
  }
}