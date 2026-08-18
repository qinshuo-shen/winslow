import { useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import "../Board/TaskModal.css";

// Self-service password change (multi-user follow-up) -- the whole point
// is that the app owner is never the one setting or knowing the friend's
// password past initial account creation, so this has to be something she
// can do herself, from her own logged-in session, with no one else
// involved. Shares TaskModal.css's overlay/panel styling, same precedent
// as NewProjectModal/ProjectRoadmapModal.

interface ChangePasswordModalProps {
  onClose: () => void;
}

export function ChangePasswordModal({ onClose }: ChangePasswordModalProps) {
  const { changePassword } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("New passwords don't match.");
      return;
    }
    setPending(true);
    try {
      await changePassword(currentPassword, newPassword);
      setSuccess(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't change your password.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="task-modal__overlay" onClick={onClose}>
      <div className="task-modal" onClick={(e) => e.stopPropagation()}>
        <header className="task-modal__header">
          <h3>Change password</h3>
          <button type="button" className="task-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        {error && <p className="task-modal__error">{error}</p>}

        {success ? (
          <>
            <p>Password changed. Any other signed-in device was logged out.</p>
            <div className="task-modal__actions">
              <button type="button" className="task-modal__save" onClick={onClose}>
                Done
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="task-modal__fields task-modal__fields--column">
              <input
                type="password"
                placeholder="Current password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
                autoFocus
                required
              />
              <input
                type="password"
                placeholder="New password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
              <input
                type="password"
                placeholder="Confirm new password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>
            <div className="task-modal__actions">
              <button type="button" onClick={onClose} disabled={pending}>
                Cancel
              </button>
              <button type="submit" className="task-modal__save" disabled={pending}>
                {pending ? "Changing..." : "Change password"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export default ChangePasswordModal;
