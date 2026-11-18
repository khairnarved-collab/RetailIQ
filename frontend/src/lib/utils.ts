import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes, letting later classes win (standard shadcn helper). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
