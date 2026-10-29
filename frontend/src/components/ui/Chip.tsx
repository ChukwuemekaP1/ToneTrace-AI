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
    verified: "bg-brand/10 text-brand border-brand/25 font-medium",
    caution: "bg-amber-500/10 text-amber-700 border-amber-500/25",
    adverse: "bg-rose-500/10 text-rose-700 border-rose-500/25",
    neutral: "bg-slate-100 text-slate-600 border-slate-200",
    champagne: "bg-champagne/20 text-slate-800 border-champagne/40",
  };

  const dotStyles = {
    verified: "bg-brand",
    caution: "bg-amber-500",
    adverse: "bg-rose-500",
    neutral: "bg-slate-400",
    champagne: "bg-champagne-dark",
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
