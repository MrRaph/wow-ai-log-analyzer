"use client";
import clsx from "clsx";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  LabelHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";

export function Card({
  children,
  className,
  interactive = false,
  id,
}: {
  children: ReactNode;
  className?: string;
  /** Adds a subtle lift + warm glow on hover. Use on list rows / clickable cards. */
  interactive?: boolean;
  id?: string;
}) {
  return (
    <div
      id={id}
      className={clsx(
        "rounded-xl border border-bg-3 bg-bg-1 p-5 shadow-[0_1px_0_rgba(255,255,255,0.04)_inset]",
        interactive &&
          "transition-[transform,border-color,box-shadow] duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-glow",
        className,
      )}
    >
      {children}
    </div>
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
}

export function Button({ variant = "primary", size = "md", className, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      className={clsx(
        "inline-flex items-center justify-center rounded-md font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg-0 disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-3 py-1.5 text-sm" : "px-4 py-2 text-sm",
        variant === "primary" && "bg-accent text-accent-fg hover:bg-accent-muted",
        variant === "secondary" && "bg-bg-3 text-zinc-100 hover:bg-bg-2",
        variant === "ghost" && "text-zinc-200 hover:bg-bg-3",
        variant === "danger" && "bg-red-600 text-white hover:bg-red-500",
        className,
      )}
    />
  );
}

export function Label({ className, ...rest }: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      {...rest}
      className={clsx("mb-1 block text-xs font-medium uppercase tracking-wide text-zinc-400", className)}
    />
  );
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Optional icon node rendered absolutely-positioned on the left side. */
  leftIcon?: ReactNode;
}

export function Input({ className, leftIcon, ...rest }: InputProps) {
  const inputEl = (
    <input
      {...rest}
      className={clsx(
        "w-full rounded-md border border-bg-3 bg-bg-2 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/50 focus:shadow-glow",
        leftIcon ? "pl-9 pr-3" : "px-3",
        className,
      )}
    />
  );
  if (!leftIcon) return inputEl;
  return (
    <div className="relative">
      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500">
        {leftIcon}
      </span>
      {inputEl}
    </div>
  );
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      className={clsx(
        "w-full rounded-md border border-bg-3 bg-bg-2 px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/50 focus:shadow-glow",
        className,
      )}
    >
      {children}
    </select>
  );
}

export function FieldError({ children }: { children: ReactNode }) {
  if (!children) return null;
  return <p className="mt-1 text-xs text-red-400">{children}</p>;
}
