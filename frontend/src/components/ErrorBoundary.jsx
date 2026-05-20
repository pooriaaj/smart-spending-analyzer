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
    console.error("Frontend render error", error, errorInfo);
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
                  <p className="auth-card-kicker">Smart Spending Analyzer</p>
                  <h2>Something went wrong.</h2>
                  <p>Please refresh the page or go back to login.</p>
                </div>

                <div className="auth-form">
                  <button type="button" className="auth-submit-button" onClick={this.handleRefresh}>
                    Refresh page
                  </button>
                  <button type="button" className="secondary-button" onClick={this.handleGoHome}>
                    Go back to login
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
