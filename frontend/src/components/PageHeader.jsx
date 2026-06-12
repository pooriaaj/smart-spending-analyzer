import { useLanguage } from "../i18n/LanguageContext";

function PageHeader({
  icon = "$",
  eyebrow,
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
    : (eyebrow ?? t("common.appName"));

  const IconContent = typeof icon === "function"
    ? (() => { const Icon = icon; return <Icon size={26} stroke={1.6} />; })()
    : icon;

  return (
    <div className="dashboard-hero app-page-header">
      <div className="app-page-title-row">
        <div className="page-logo-mark" aria-hidden="true">
          {IconContent}
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
