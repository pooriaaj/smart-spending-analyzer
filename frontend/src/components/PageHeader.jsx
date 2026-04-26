import { useNavigate } from "react-router-dom";

const APP_DESTINATIONS = [
  { label: "Dashboard", path: "/dashboard" },
  { label: "Transactions", path: "/transactions" },
  { label: "Smart Import", path: "/import" },
  { label: "Money Map", path: "/money-map" },
  { label: "Analytics", path: "/analytics" },
  { label: "Budgets", path: "/budgets" },
  { label: "Simulator", path: "/simulator" },
  { label: "Assistant", path: "/assistant" },
  { label: "Accounts", path: "/accounts" },
  { label: "Profile & Settings", path: "/profile" },
];

function PageHeader({
  icon = "$",
  eyebrow = "Smart Spending Analyzer",
  title,
  subtitle,
  section = "App",
  current,
  actions,
}) {
  const navigate = useNavigate();

  const handleDestinationChange = (event) => {
    const nextPath = event.target.value;
    if (nextPath) {
      navigate(nextPath);
      event.target.value = "";
    }
  };

  return (
    <div className="dashboard-hero app-page-header">
      <div className="app-page-title-row">
        <div className="page-logo-mark" aria-hidden="true">
          {icon}
        </div>

        <div>
          <p className="eyebrow-text">{eyebrow}</p>
          <div className="app-breadcrumb">
            <span>Settings</span>
            <span>/</span>
            <span>{section}</span>
            <span>/</span>
            <strong>{current || title}</strong>
          </div>
          <h1>{title}</h1>
          <p className="hero-subtitle">{subtitle}</p>
        </div>
      </div>

      <div className="header-actions professional-header-actions">
        <label className="nav-dropdown-label" htmlFor={`nav-${title.replace(/\s+/g, "-").toLowerCase()}`}>
          Go to
        </label>
        <select
          id={`nav-${title.replace(/\s+/g, "-").toLowerCase()}`}
          className="nav-dropdown"
          defaultValue=""
          onChange={handleDestinationChange}
        >
          <option value="" disabled>
            Choose page
          </option>
          {APP_DESTINATIONS.map((item) => (
            <option key={item.path} value={item.path}>
              {item.label}
            </option>
          ))}
        </select>

        <button className="premium-header-button" type="button" onClick={() => navigate("/profile#plans")}>
          View Premium
        </button>

        {actions}
      </div>
    </div>
  );
}

export default PageHeader;
