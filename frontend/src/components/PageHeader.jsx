import { useNavigate } from "react-router-dom";
import { useLanguage } from "../i18n/LanguageContext";

const APP_DESTINATIONS = [
  { labelKey: "common.analytics", path: "/analytics" },
  { labelKey: "common.smartImport", path: "/import" },
  { labelKey: "common.transactions", path: "/transactions" },
  { labelKey: "common.budgets", path: "/budgets" },
  { labelKey: "common.assistant", path: "/assistant" },
  { labelKey: "common.profileSettings", path: "/profile" },
];

function PageHeader({
  icon = "$",
  eyebrow = "Smart Spending Analyzer",
  eyebrowKey,
  title,
  titleKey,
  subtitle,
  subtitleKey,
  actions,
}) {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const resolvedTitle = titleKey ? t(titleKey) : title;
  const resolvedSubtitle = subtitleKey ? t(subtitleKey) : subtitle;
  const resolvedEyebrow = eyebrowKey
    ? t(eyebrowKey)
    : eyebrow === "Smart Spending Analyzer"
    ? t("common.appName")
    : eyebrow;
  const navId = `nav-${String(resolvedTitle || "page").replace(/\s+/g, "-").toLowerCase()}`;

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
          <p className="eyebrow-text">{resolvedEyebrow}</p>
          <h1>{resolvedTitle}</h1>
          <p className="hero-subtitle">{resolvedSubtitle}</p>
        </div>
      </div>

      <div className="header-actions professional-header-actions">
        <label className="nav-dropdown-label" htmlFor={navId}>
          {t("common.appMenu")}
        </label>
        <select
          id={navId}
          className="nav-dropdown"
          defaultValue=""
          onChange={handleDestinationChange}
        >
          <option value="" disabled>
            {t("common.openPage")}
          </option>
          {APP_DESTINATIONS.map((item) => (
            <option key={item.path} value={item.path}>
              {t(item.labelKey)}
            </option>
          ))}
        </select>

        <button className="premium-header-button" type="button" onClick={() => navigate("/profile#plans")}>
          {t("common.viewPremium")}
        </button>

        {actions}
      </div>
    </div>
  );
}

export default PageHeader;
