import * as React from "react";
import { cn } from "@/lib/utils";

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...p }, ref) => (
  <div ref={ref} className={cn("rounded-xl border bg-card text-card-foreground shadow-sm", className)} {...p} />
));
Card.displayName = "Card";
export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...p }, ref) => (
  <div ref={ref} className={cn("flex flex-col gap-1 p-4 sm:p-5", className)} {...p} />
));
CardHeader.displayName = "CardHeader";
export const CardTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(({ className, ...p }, ref) => (
  <h3 ref={ref} className={cn("text-[15px] font-semibold leading-tight tracking-tight", className)} {...p} />
));
CardTitle.displayName = "CardTitle";
export const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(({ className, ...p }, ref) => (
  <p ref={ref} className={cn("text-xs text-muted-foreground sm:text-sm", className)} {...p} />
));
CardDescription.displayName = "CardDescription";
export const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...p }, ref) => (
  <div ref={ref} className={cn("p-4 pt-0 sm:p-5 sm:pt-0", className)} {...p} />
));
CardContent.displayName = "CardContent";
