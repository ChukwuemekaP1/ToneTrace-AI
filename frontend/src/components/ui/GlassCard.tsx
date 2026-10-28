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
    default: "bg-[#10161C]/80 backdrop-blur-md border border-white/8 shadow-sm",
    elevated: "bg-[#172027]/90 backdrop-blur-lg border border-white/12 shadow-glass",
    interactive:
      "bg-[#10161C]/80 backdrop-blur-md border border-white/8 hover:border-emerald-500/30 hover:bg-[#131B22]/90 cursor-pointer active:scale-[0.99]",
    accent:
      "bg-gradient-to-b from-emerald-950/20 to-[#10161C]/90 backdrop-blur-md border border-emerald-500/20 shadow-glow",
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
