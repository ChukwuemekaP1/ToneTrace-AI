/**
 * Frontend environment configuration and runtime validation.
 */

interface AppConfig {
  apiBaseUrl: string;
  isProduction: boolean;
  isDevelopment: boolean;
  appVersion: string;
  enableDevShowcase: boolean;
}

function parseEnv(): AppConfig {
  const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "").trim();
  const nodeEnv = import.meta.env.MODE || "development";
  const appVersion = import.meta.env.VITE_APP_VERSION || "0.1.0";
  const enableDevShowcase = import.meta.env.VITE_ENABLE_DEV_SHOWCASE !== "false";

  // Validate API URL format if explicitly provided
  if (apiBaseUrl && !apiBaseUrl.startsWith("http://") && !apiBaseUrl.startsWith("https://") && !apiBaseUrl.startsWith("/")) {
    console.warn(`[Config] VITE_API_BASE_URL '${apiBaseUrl}' should be an absolute URL or start with '/' for proxying.`);
  }

  return {
    apiBaseUrl: apiBaseUrl || "", // Empty string means use relative paths with Vite proxy
    isProduction: nodeEnv === "production",
    isDevelopment: nodeEnv === "development",
    appVersion,
    enableDevShowcase,
  };
}

export const env = parseEnv();
