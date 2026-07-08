import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

/** 크래시 시 남색 빈 화면 대신 HUD 에러 패널을 띄운다. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="flex h-full items-center justify-center bg-surface-0">
        <div className="hud-clip bg-red-ops p-px">
          <div className="hud-clip max-w-md bg-surface-1 p-6">
            <h1 className="font-display text-sm font-bold uppercase tracking-[0.14em] text-red-ops">
              System Fault
            </h1>
            <p className="mt-3 break-all font-mono text-[11px] text-text-mid">
              {this.state.error.message}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="mt-5 border border-hud px-4 py-2 font-display text-xs font-semibold uppercase tracking-[0.1em] text-hud-active transition-colors hover:border-hud-active active:scale-[0.97]"
            >
              다시 시작
            </button>
          </div>
        </div>
      </div>
    );
  }
}
