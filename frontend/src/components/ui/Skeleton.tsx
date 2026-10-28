import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "text" | "rectangular" | "circular" | "card";
  width?: string | number;
  height?: string | number;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  className,
  variant = "text",
  width,
  height,
  style,
  ...props
}) => {
  const baseStyles =
    "relative overflow-hidden bg-white/5 animate-pulse select-none " +
    "after:absolute after:inset-0 after:translate-x-[-100%] after:animate-[shimmer_1.8s_infinite] " +
    "after:bg-gradient-to-r after:from-transparent after:via-white/[0.04] after:to-transparent";

  const variantStyles = {
    text: "h-4 rounded-md w-full",
    rectangular: "rounded-xl",
    circular: "rounded-full shrink-0",
    card: "h-28 rounded-2xl border border-white/5",
  };

  const computedStyle: React.CSSProperties = {
    ...style,
    width: width !== undefined ? width : undefined,
    height: height !== undefined ? height : undefined,
  };

  return (
    <div
      className={twMerge(clsx(baseStyles, variantStyles[variant], className))}
      style={computedStyle}
      {...props}
    />
  );
};
