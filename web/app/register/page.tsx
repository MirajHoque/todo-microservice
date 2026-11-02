// ============================================================
// app/register/page.tsx — the /register page.
//
// Same form as /login (see components/auth-form.tsx), but it calls
// POST /api/v1/auth/register instead of /auth/login.
// ============================================================

import type { Metadata } from "next";

import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Register · Todo" };

export default function RegisterPage() {
  return <AuthForm mode="register" />;
}
