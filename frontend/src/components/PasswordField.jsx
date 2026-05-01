import { useState } from "react";
import { useLanguage } from "../i18n/LanguageContext";

function PasswordField({
  label,
  value,
  onChange,
  placeholder,
  name,
  autoComplete,
  required = false,
}) {
  const [showPassword, setShowPassword] = useState(false);
  const { isFrench } = useLanguage();
  const showText = isFrench ? "Afficher" : "Show";
  const hideText = isFrench ? "Masquer" : "Hide";

  return (
    <div className="auth-field">
      <label htmlFor={name}>{label}</label>

      <div className="password-input-wrapper">
        <input
          id={name}
          name={name}
          type={showPassword ? "text" : "password"}
          placeholder={placeholder}
          value={value}
          onChange={onChange}
          autoComplete={autoComplete}
          required={required}
        />

        <button
          type="button"
          className="password-toggle-button"
          onClick={() => setShowPassword((prev) => !prev)}
          aria-label={`${showPassword ? hideText : showText} ${label}`}
          aria-pressed={showPassword}
        >
          {showPassword ? hideText : showText}
        </button>
      </div>
    </div>
  );
}

export default PasswordField;
