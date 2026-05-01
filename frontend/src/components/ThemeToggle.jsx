import { useLanguage } from "../i18n/LanguageContext";

function ThemeToggle({ theme, onToggle }) {
  const { t } = useLanguage();

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={onToggle}
      aria-label={t("theme.toggle")}
      title={theme === "light" ? t("theme.switchToDark") : t("theme.switchToLight")}
    >
      <span className="theme-toggle-icon">
        {theme === "light" ? "Moon" : "Sun"}
      </span>
      <span className="theme-toggle-text">
        {theme === "light" ? t("theme.dark") : t("theme.light")}
      </span>
    </button>
  );
}

export default ThemeToggle;
