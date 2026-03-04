import { Component } from "react";

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, retryCount: 0 };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("ErrorBoundary caught:", error, info);
  }

  handleRetry = () => {
    this.setState((prev) => ({ hasError: false, error: null, retryCount: prev.retryCount + 1 }));
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      const canRetry = this.state.retryCount < 2;
      return (
        <div className="error-boundary-fallback">
          <p>Something went wrong rendering this content.</p>
          {canRetry && (
            <button type="button" onClick={this.handleRetry}>
              Try Again
            </button>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
