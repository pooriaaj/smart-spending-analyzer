import React from "react";

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    // Intentional: error boundaries must be class components and cannot use hooks.
    // Log render errors so they appear in production log aggregators.
    if (typeof window !== "undefined" && window.__reportError) {
      window.__reportError(error, errorInfo);
    }
  }

  handleGoHome = () => {
    window.location.href = "/";
  };

  handleRefresh = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="auth-shell">
          <div className="auth-layout auth-layout-single">
            <div className="auth-panel auth-panel-centered">
              <div className="auth-card">
                <div className="auth-card-header">
                  <p className="auth-card-kicker">Zero2Asset</p>
                  <h2>Something went wrong.</h2>
                  <p>Please refresh the page or return to login.</p>
                </div>

                <div className="auth-form">
                  <button type="button" className="auth-submit-button" onClick={this.handleRefresh}>
                    Refresh page
                  </button>
                  <button type="button" className="secondary-button" onClick={this.handleGoHome}>
                    Return to login
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
