"use client";

import { AlertTriangle } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="empty-state" style={{ margin: 24 }}>
          <AlertTriangle size={24} />
          <h2>Something went wrong</h2>
          <p>{this.state.error.message}</p>
          <button
            onClick={() => this.setState({ error: null })}
            className="secondary-action compact"
          >
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
