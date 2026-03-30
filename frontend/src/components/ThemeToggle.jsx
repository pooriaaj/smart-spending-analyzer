function ThemeToggle({ theme, onToggle }) {
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={onToggle}
      aria-label="Toggle theme"
      title={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
    >
      <span className="theme-toggle-icon">
        {theme === "light" ? "🌙" : "☀️"}
      </span>
      <span className="theme-toggle-text">
        {theme === "light" ? "Dark" : "Light"}
      </span>
    </button>
  );
}

export default ThemeToggle;