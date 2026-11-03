// ============================================================
// lib/session.ts — where the logged-in user's token is kept.
//
// After login the API returns a JWT. The browser must send it on
// every protected request ("Authorization: Bearer <token>"), so we
// keep it in localStorage — the same place the old Go-rendered
// pages (services/api/web/templates) keep it.
//
// localStorage only exists in the browser, not on the Next.js
// server, so every function checks for `window` first.
//
// Trade-off (fine for learning, revisit later): any JavaScript on
// the page can read localStorage. A more secure setup keeps the
// token in an httpOnly cookie that JavaScript cannot see.
// ============================================================

const TOKEN_KEY = "token";
const EMAIL_KEY = "user_email";

const inBrowser = () => typeof window !== "undefined";

// saveSession stores the token and email after login/register.
export function saveSession(token: string, email: string): void {
  if (!inBrowser()) return;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(EMAIL_KEY, email);
}

// getToken returns the saved JWT, or null when logged out.
export function getToken(): string | null {
  return inBrowser() ? localStorage.getItem(TOKEN_KEY) : null;
}

// getEmail returns the logged-in user's email, or null.
export function getEmail(): string | null {
  return inBrowser() ? localStorage.getItem(EMAIL_KEY) : null;
}

// clearSession forgets the user (logout, or the token expired).
export function clearSession(): void {
  if (!inBrowser()) return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
}
