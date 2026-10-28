import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { Loader2 } from "lucide-react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "danger" | "ghost" | "champagne";
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = "primary",
      size = "md",
      isLoading = false,
      disabled,
      children,
      leftIcon,
      rightIcon,
      ...props
    },
    ref
  ) => {
    const baseStyles =
      "relative inline-flex items-center justify-center font-medium transition-all duration-150 select-none " +
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[#080C0F] " +
      "disabled:opacity-50 disabled:pointer-events-none active:scale-[0.98]";

    const sizeStyles = {
      sm: "h-8 px-3 text-xs rounded-md gap-1.5",
      md: "h-10 px-4 text-sm rounded-lg gap-2",
      lg: "h-12 px-6 text-base rounded-xl gap-2.5",
    };

    const variantStyles = {
      primary:
        "bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold shadow-sm hover:shadow-glow",
      secondary:
        "bg-surface-elevated hover:bg-surface-elevated/80 text-slate-200 border border-white/10 hover:border-white/20",
      outline:
        "bg-transparent hover:bg-white/5 text-slate-200 border border-white/15 hover:border-white/30",
      danger:
        "bg-adverse/20 hover:bg-adverse/30 text-rose-300 border border-adverse/40 hover:border-adverse/60",
      ghost: "bg-transparent hover:bg-white/5 text-slate-300 hover:text-white",
      champagne:
        "bg-champagne hover:bg-champagne-light text-slate-950 font-semibold shadow-sm",
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={twMerge(clsx(baseStyles, sizeStyles[size], variantStyles[variant], className))}
        {...props}
      >
        {isLoading && <Loader2 className="w-4 h-4 animate-spin text-current" />}
        {!isLoading && leftIcon}
        <span>{children}</span>
        {!isLoading && rightIcon}
      </button>
    );
  }
);

Button.displayName = "Button";
