// ============================================================
// app/login/page.tsx — the /login page.
//
// App Router: the folder name is the URL (app/login → /login),
// and page.tsx is what gets shown there. All the logic lives in
// the shared AuthForm component.
// ============================================================

import type { Metadata } from "next";

import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Log in · Todo" };

export default function LoginPage() {
  return <AuthForm mode="login" />;
}
