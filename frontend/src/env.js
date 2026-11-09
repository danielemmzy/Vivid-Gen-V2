import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

export const env = createEnv({
  /**
   * Specify your server-side environment variables schema here. This way you can ensure the app
   * isn't built with invalid env vars.
   */
  server: {
    DATABASE_URL: z.string().url(),
    NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
    BACKEND_API_URL: z.string().url(),
    BACKEND_INTERNAL_SECRET: z.string().min(32),
    POLAR_ACCESS_TOKEN: z.string(),
    POLAR_SERVER: z.enum(["sandbox", "production"]).default("sandbox"),
    POLAR_WEBHOOK_SECRET: z.string(),
    BETTER_AUTH_SECRET: z.string().min(32),
  },

  /**
   * Specify your client-side environment variables schema here. This way you can ensure the app
   * isn't built with invalid env vars. To expose them to the client, prefix them with
   * `NEXT_PUBLIC_`.
   */
  client: {
    // NEXT_PUBLIC_CLIENTVAR: z.string(),
    NEXT_PUBLIC_SMALL_CREDIT_ID: z.string(),
    NEXT_PUBLIC_MEDIUM_CREDIT_ID: z.string(),
    NEXT_PUBLIC_LARGE_CREDIT_ID: z.string()
  },

  /**
   * You can't destruct `process.env` as a regular object in the Next.js edge runtimes (e.g.
   * middlewares) or client-side so we need to destruct manually.
   */
  runtimeEnv: {
    DATABASE_URL: process.env.DATABASE_URL,
    NODE_ENV: process.env.NODE_ENV,
    BACKEND_API_URL: process.env.BACKEND_API_URL,
    BACKEND_INTERNAL_SECRET: process.env.BACKEND_INTERNAL_SECRET,
    POLAR_ACCESS_TOKEN: process.env.POLAR_ACCESS_TOKEN,
    POLAR_SERVER: process.env.POLAR_SERVER,
    NEXT_PUBLIC_SMALL_CREDIT_ID: process.env.NEXT_PUBLIC_SMALL_CREDIT_ID,
    NEXT_PUBLIC_MEDIUM_CREDIT_ID: process.env.NEXT_PUBLIC_MEDIUM_CREDIT_ID,
    NEXT_PUBLIC_LARGE_CREDIT_ID: process.env.NEXT_PUBLIC_LARGE_CREDIT_ID,
    POLAR_WEBHOOK_SECRET: process.env.POLAR_WEBHOOK_SECRET,
    BETTER_AUTH_SECRET: process.env.BETTER_AUTH_SECRET,
  },
  /**
   * Run `build` or `dev` with `SKIP_ENV_VALIDATION` to skip env validation. This is especially
   * useful for Docker builds.
   */
  skipValidation: !!process.env.SKIP_ENV_VALIDATION,
  /**
   * Makes it so that empty strings are treated as undefined. `SOME_VAR: z.string()` and
   * `SOME_VAR=''` will throw an error.
   */
  emptyStringAsUndefined: true,
});
