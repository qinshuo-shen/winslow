import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import "./LoginPage.css";

// Multi-user follow-up: plain username/password. No self-serve "forgot
// password" flow -- with no email integration (deliberately, see
// procrastination_tool/auth.py's docstring), there's no channel to send a
// reset link through anyway. The hint below just points at the real
// recovery path: the account owner running scripts/reset_password.py.

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      const redirectTo = (location.state as { from?: string } | null)?.from ?? "/tasks";
      navigate(redirectTo, { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? "Incorrect username or password." : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <form className="login-page__form" onSubmit={handleSubmit}>
        <h1 className="login-page__title">Winslow</h1>
        <label className="login-page__field">
          Username
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </label>
        <label className="login-page__field">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && <p className="login-page__error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Signing in..." : "Sign in"}
        </button>
        <p className="login-page__hint">
          Forgot your password? Ask whoever set up your account to reset it for you.
        </p>
      </form>
    </div>
  );
}

export default LoginPage;
