import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { ApiError, UNAUTHORIZED_EVENT, apiPost } from "../api/client";

// Multi-user follow-up: the single source of truth for "who's logged in,"
// consumed by App.tsx's route guard and NavBar's "Signed in as"/logout
// action. Reads GET /api/auth/me once on mount (a bare 401 there just
// means "not logged in yet," not a real error to surface) and otherwise
// only changes in response to an explicit login()/logout() call or a
// UNAUTHORIZED_EVENT from client.ts -- e.g. the session expired or was
// revoked from another tab -- so every page reflects "logged out"
// immediately without needing its own 401 handling.

interface AuthUser {
  username: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/auth/me")
      .then((res) => (res.ok ? res.json() : null))
      .then((data: AuthUser | null) => setUser(data))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => setUser(null);
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const result = await apiPost<AuthUser>("/auth/login", { username, password });
    setUser(result);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiPost("/auth/logout");
    } catch (e) {
      // A logout call that itself 401s (session already gone) still means
      // "logged out" from the frontend's perspective -- any other error
      // is unexpected but shouldn't block clearing local state either.
      if (!(e instanceof ApiError)) throw e;
    } finally {
      setUser(null);
    }
  }, []);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    // Doesn't touch `user` -- the username isn't changing, and the
    // backend keeps this exact session alive (see auth.change_password's
    // keep_token), so there's nothing here that should log the caller out.
    await apiPost("/auth/change-password", {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, changePassword }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() must be used within an AuthProvider");
  return ctx;
}
