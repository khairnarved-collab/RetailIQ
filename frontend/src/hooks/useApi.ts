import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/services/api";
import type { FilterOptions } from "@/services/types";

/** GET with caching, loading and error state (TanStack Query). */
export function useApiQuery<T>(key: unknown[], path: string | null, opts?: Partial<UseQueryOptions<T>>) {
  return useQuery<T>({
    queryKey: key,
    queryFn: () => api.get<T>(path as string),
    enabled: path !== null && (opts?.enabled ?? true),
    ...opts,
  });
}

/** Filter options (stores, categories, products, date range) - shared by many pages. */
export function useFilterOptions() {
  return useApiQuery<FilterOptions>(["filters"], "/meta/filters", { staleTime: 5 * 60_000 });
}

/** POST/PATCH/... with automatic error toast and cache invalidation. */
export function useApiMutation<TBody, TRes>(fn: (b: TBody) => Promise<TRes>, invalidate: unknown[][] = [], success?: string) {
  const qc = useQueryClient();
  return useMutation<TRes, Error, TBody>({
    mutationFn: fn,
    onSuccess: () => {
      invalidate.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      if (success) toast.success(success);
    },
    onError: (e) => toast.error(e.message),
  });
}
