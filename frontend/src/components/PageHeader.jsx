import { useLanguage } from "../i18n/LanguageContext";

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
  const { t } = useLanguage();
  const resolvedTitle = titleKey ? t(titleKey) : title;
  const resolvedSubtitle = subtitleKey ? t(subtitleKey) : subtitle;
  const resolvedEyebrow = eyebrowKey
    ? t(eyebrowKey)
    : eyebrow === "Smart Spending Analyzer"
    ? t("common.appName")
    : eyebrow;

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

      {actions && (
        <div className="header-actions professional-header-actions">
          {actions}
        </div>
      )}
    </div>
  );
}

export default PageHeader;
