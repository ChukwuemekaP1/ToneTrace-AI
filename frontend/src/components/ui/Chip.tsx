import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "verified" | "caution" | "adverse" | "neutral" | "champagne";
  size?: "sm" | "md";
  showDot?: boolean;
}

export const Chip: React.FC<ChipProps> = ({
  className,
  variant = "neutral",
  size = "md",
  showDot = false,
  children,
  ...props
}) => {
  const baseStyles = "inline-flex items-center font-medium border transition-colors select-none";

  const sizeStyles = {
    sm: "px-2 py-0.5 text-xxs rounded-md gap-1",
    md: "px-2.5 py-1 text-xs rounded-lg gap-1.5",
  };

  const variantStyles = {
    verified: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
    caution: "bg-amber-500/10 text-amber-300 border-amber-500/25",
    adverse: "bg-rose-500/10 text-rose-300 border-rose-500/25",
    neutral: "bg-white/5 text-slate-300 border-white/10",
    champagne: "bg-champagne/10 text-champagne border-champagne/30",
  };

  const dotStyles = {
    verified: "bg-emerald-400",
    caution: "bg-amber-400",
    adverse: "bg-rose-400",
    neutral: "bg-slate-400",
    champagne: "bg-champagne",
  };

  return (
    <span
      className={twMerge(clsx(baseStyles, sizeStyles[size], variantStyles[variant], className))}
      {...props}
    >
      {showDot && (
        <span
          className={twMerge(
            clsx("w-1.5 h-1.5 rounded-full shrink-0", dotStyles[variant])
          )}
        />
      )}
      {children}
    </span>
  );
};
