import { useState } from "react";

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
          aria-label={showPassword ? `Hide ${label}` : `Show ${label}`}
          aria-pressed={showPassword}
        >
          {showPassword ? "Hide" : "Show"}
        </button>
      </div>
    </div>
  );
}

export default PasswordField;