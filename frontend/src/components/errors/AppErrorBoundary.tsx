import { Component, type ErrorInfo, type ReactNode } from "react";
import ErrorFallbackPage from "@/pages/errors/ErrorFallbackPage";

interface AppErrorBoundaryProps {
  children: ReactNode;
}

interface AppErrorBoundaryState {
  hasError: boolean;
}

class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error("Uncaught render error", error, errorInfo);
    }
  }

  private reset = () => {
    this.setState({ hasError: false });
  };

  render() {
    if (this.state.hasError) {
      return <ErrorFallbackPage onReset={this.reset} />;
    }

    return this.props.children;
  }
}

export default AppErrorBoundary;
