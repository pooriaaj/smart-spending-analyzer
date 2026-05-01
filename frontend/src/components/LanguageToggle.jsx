import { SUPPORTED_LANGUAGES, useLanguage } from "../i18n/LanguageContext";

function LanguageToggle() {
  const { language, setLanguage, t } = useLanguage();
  const nextLanguage = language === "fr" ? "en" : "fr";

  return (
    <div className="language-toggle" aria-label={t("language.label")}>
      {Object.values(SUPPORTED_LANGUAGES).map((item) => (
        <button
          key={item.code}
          type="button"
          className={language === item.code ? "language-toggle-option active" : "language-toggle-option"}
          onClick={() => setLanguage(item.code)}
          aria-pressed={language === item.code}
        >
          {item.shortLabel}
        </button>
      ))}
      <span className="language-toggle-label">
        {nextLanguage === "fr" ? t("language.switchToFrench") : t("language.switchToEnglish")}
      </span>
    </div>
  );
}

export default LanguageToggle;
