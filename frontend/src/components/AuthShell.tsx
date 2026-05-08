import type { ReactNode } from "react";

// Full-bleed dark hero background for auth pages (login, register,
// forgot-password, reset-password, accept-invite). Centers the form
// vertically + horizontally and layers a translucent gradient over the
// hero image so the form copy stays legible regardless of the underlying
// image area.
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-[calc(100vh-4rem)] items-center justify-center overflow-hidden px-4 py-12">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 bg-[url('/brand/hero-login.png')] bg-cover bg-center opacity-50"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-bg-0/40 via-bg-0/60 to-bg-0"
      />
      <div className="w-full max-w-md">{children}</div>
    </div>
  );
}
