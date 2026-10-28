/**
 * Dashboard Data Service
 *
 * Provides typed, cached, and deduplicated access to:
 * - User routines (/api/v1/me/routines) & routine completion (/api/v1/me/routines/{id}/completions)
 * - User reminder preferences (/api/v1/me/reminders)
 * - Recent skin scans (/api/v1/skin/scans) & longitudinal story (/api/v1/skin/story)
 * - Product discovery feed (/api/v1/discovery/products)
 *
 * Implements in-memory TTL caching (60s) with in-flight promise deduplication
 * to prevent duplicate concurrent network requests during tab switching and navigation.
 */

import { apiClient } from "./client";
import {
  RoutineListResponse,
  RoutineCompletionResponse,
  ReminderPreferenceResponse,
  SkinScanListResponse,
  SkinScanResponse,
  SkinStoryResponse,
  DiscoveryProductListResponse,
} from "./types";

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

const DEFAULT_CACHE_TTL_MS = 60 * 1000; // 60 seconds

export class DashboardService {
  private cache: Map<string, CacheEntry<unknown>> = new Map();
  private inFlightPromises: Map<string, Promise<unknown>> = new Map();

  /**
   * Internal deduplicated & cached fetch helper
   */
  private async cachedFetch<T>(
    key: string,
    fetcher: () => Promise<T>,
    forceRefresh = false,
    ttlMs: number = DEFAULT_CACHE_TTL_MS
  ): Promise<T> {
    const now = Date.now();

    if (!forceRefresh) {
      const cached = this.cache.get(key) as CacheEntry<T> | undefined;
      if (cached && now - cached.timestamp < ttlMs) {
        return cached.data;
      }

      // Check if already in-flight
      const inFlight = this.inFlightPromises.get(key) as Promise<T> | undefined;
      if (inFlight) {
        return inFlight;
      }
    }

    const promise = (async () => {
      try {
        const result = await fetcher();
        this.cache.set(key, { data: result, timestamp: Date.now() });
        return result;
      } finally {
        this.inFlightPromises.delete(key);
      }
    })();

    this.inFlightPromises.set(key, promise);
    return promise;
  }

  /**
   * Fetch active and configured routines for the user
   */
  public async getRoutines(forceRefresh = false): Promise<RoutineListResponse> {
    return this.cachedFetch<RoutineListResponse>(
      "routines",
      () =>
        apiClient.get<RoutineListResponse>("/api/v1/me/routines", {
          params: { page: 1, page_size: 20 },
        }),
      forceRefresh
    );
  }

  /**
   * Fetch user's reminder preferences and timezone configuration
   */
  public async getReminders(forceRefresh = false): Promise<ReminderPreferenceResponse> {
    return this.cachedFetch<ReminderPreferenceResponse>(
      "reminders",
      () => apiClient.get<ReminderPreferenceResponse>("/api/v1/me/reminders"),
      forceRefresh
    );
  }

  /**
   * Fetch the most recent skin scan (if any)
   */
  public async getRecentScan(forceRefresh = false): Promise<SkinScanResponse | null> {
    return this.cachedFetch<SkinScanResponse | null>(
      "recent_scan",
      async () => {
        const res = await apiClient.get<SkinScanListResponse>("/api/v1/skin/scans", {
          params: { limit: 1, offset: 0 },
        });
        if (res && res.items && res.items.length > 0) {
          return res.items[0];
        }
        return null;
      },
      forceRefresh
    );
  }

  /**
   * Fetch longitudinal Skin Story summary
   */
  public async getSkinStory(forceRefresh = false): Promise<SkinStoryResponse | null> {
    return this.cachedFetch<SkinStoryResponse | null>(
      "skin_story",
      () => apiClient.get<SkinStoryResponse>("/api/v1/skin/story"),
      forceRefresh
    );
  }

  /**
   * Fetch real product discovery feed from backend catalogue
   */
  public async getDiscoveryFeed(forceRefresh = false): Promise<DiscoveryProductListResponse> {
    return this.cachedFetch<DiscoveryProductListResponse>(
      "discovery_feed",
      () =>
        apiClient.get<DiscoveryProductListResponse>("/api/v1/discovery/products", {
          params: { page: 1, page_size: 4 },
        }),
      forceRefresh
    );
  }

  /**
   * Record a routine completion and invalidate routines cache
   */
  public async recordRoutineCompletion(
    routineId: string,
    timeOfDay: "morning" | "evening" | string = "morning"
  ): Promise<RoutineCompletionResponse> {
    const response = await apiClient.post<RoutineCompletionResponse>(
      `/api/v1/me/routines/${routineId}/completions`,
      {
        completion_status: "completed",
        time_of_day: timeOfDay,
        completed_step_ids: [],
      }
    );
    // Invalidate routines cache so next load or caller displays refreshed completion count
    this.invalidateCache("routines");
    return response;
  }

  /**
   * Invalidate specific or all cached keys
   */
  public invalidateCache(key?: "routines" | "reminders" | "recent_scan" | "skin_story" | "discovery_feed"): void {
    if (key) {
      this.cache.delete(key);
    } else {
      this.cache.clear();
    }
  }
}

export const dashboardService = new DashboardService();
