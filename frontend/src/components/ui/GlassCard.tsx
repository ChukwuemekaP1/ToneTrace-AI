import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "elevated" | "interactive" | "accent";
  padding?: "none" | "sm" | "md" | "lg";
}

export const GlassCard: React.FC<GlassCardProps> = ({
  className,
  variant = "default",
  padding = "md",
  children,
  ...props
}) => {
  const baseStyles = "rounded-2xl transition-all duration-200 relative overflow-hidden";

  const paddingStyles = {
    none: "p-0",
    sm: "p-3",
    md: "p-4",
    lg: "p-6",
  };

  const variantStyles = {
    default: "bg-white/95 backdrop-blur-md border border-slate-200/80 shadow-soft text-slate-800",
    elevated: "bg-white backdrop-blur-lg border border-slate-200 shadow-card text-slate-800",
    interactive:
      "bg-white/95 backdrop-blur-md border border-slate-200 hover:border-brand/40 hover:shadow-card cursor-pointer active:scale-[0.99] text-slate-800",
    accent:
      "bg-gradient-to-b from-brand/5 to-white/95 backdrop-blur-md border border-brand/20 shadow-soft text-slate-800",
  };

  return (
    <div
      className={twMerge(clsx(baseStyles, paddingStyles[padding], variantStyles[variant], className))}
      {...props}
    >
      {children}
    </div>
  );
};
