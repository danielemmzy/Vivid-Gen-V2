
import { betterAuth } from "better-auth";
import { prismaAdapter } from "better-auth/adapters/prisma";
import { Polar } from "@polar-sh/sdk";
import {
  polar,
  checkout,
  portal,
  webhooks,
} from "@polar-sh/better-auth";

import { db } from "~/server/db";
import { backendFetch } from "~/lib/backend";
import { env } from "~/env";

const polarClient = new Polar({
  accessToken: env.POLAR_ACCESS_TOKEN,
  server: env.POLAR_SERVER,
});

export const auth = betterAuth({
  secret: env.BETTER_AUTH_SECRET,
  database: prismaAdapter(db, {
    provider: "postgresql",
  }),

  emailAndPassword: {
    enabled: true,
  },

  plugins: [
    polar({
      client: polarClient,
      createCustomerOnSignUp: true,

      use: [
        checkout({
          products: [
            {
              productId: env.NEXT_PUBLIC_SMALL_CREDIT_ID,
              slug: "small",
            },
            {
              productId: env.NEXT_PUBLIC_MEDIUM_CREDIT_ID,
              slug: "medium",
            },
            {
              productId: env.NEXT_PUBLIC_LARGE_CREDIT_ID,
              slug: "large",
            },
          ],
          successUrl: "/?purchase_success=true",
          authenticatedUsersOnly: true,
        }),

        portal(),

        webhooks({
          secret: env.POLAR_WEBHOOK_SECRET,

          onOrderPaid: async (order) => {
            const externalCustomerId =
              order.data.customer.externalId;

            if (!externalCustomerId) {
              throw new Error(
                "No external customer ID found",
              );
            }

            const productId = order.data.productId;

            // Ignore orders without a product ID.
            if (!productId) {
              return;
            }

            const creditProductIds = new Set<string>([
              env.NEXT_PUBLIC_SMALL_CREDIT_ID,
              env.NEXT_PUBLIC_MEDIUM_CREDIT_ID,
              env.NEXT_PUBLIC_LARGE_CREDIT_ID,
            ]);

            // Ignore products that do not represent credit top-ups.
            if (!creditProductIds.has(productId)) {
              return;
            }

            // FastAPI owns the authoritative credit balance and
            // immutable ledger. Polar's order ID provides the
            // idempotency key for webhook retries.
            await backendFetch<{
              credits_added: number;
              balance: number;
              duplicate_webhook: boolean;
            }>(
              externalCustomerId,
              "/credits/purchase",
              {
                method: "POST",
                body: JSON.stringify({
                  order_id: order.data.id,
                  product_id: productId,
                }),
              },
            );
          },
        }),
      ],
    }),
  ],
});
