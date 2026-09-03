import { betterAuth } from "better-auth";
import { prismaAdapter } from "better-auth/adapters/prisma";
import { db } from "~/server/db";
import { Polar } from "@polar-sh/sdk";
import { env } from "~/env";
import {
  polar,
  checkout,
  portal,
  usage,
  webhooks,
} from "@polar-sh/better-auth";
import { externalCustomerIDFilterToJSON } from "@polar-sh/sdk/models/operations/subscriptionslist.js";

const polarClient = new Polar({
  accessToken: env.POLAR_ACCESS_TOKEN,
  server: "sandbox",
});

export const auth = betterAuth({
  database: prismaAdapter(db, {
    provider: "postgresql", // or "mysql", "postgresql", ...etc
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
            const exeternalCustomerId = order.data.customer.externalId;
            if (!exeternalCustomerId) {
              throw new Error("no external customer id found");
            }
            const productId = order.data.productId;
            let creditsToAdd = 0;
            switch (productId) {
              case env.NEXT_PUBLIC_SMALL_CREDIT_ID:
                creditsToAdd = 10;
                break;

              case env.NEXT_PUBLIC_MEDIUM_CREDIT_ID:
                creditsToAdd = 25;
                break;

              case env.NEXT_PUBLIC_LARGE_CREDIT_ID:
                creditsToAdd = 50;
                break;
            }
            await db.user.update({
              where: { id: exeternalCustomerId },
              data: {
                credits: {
                  increment: creditsToAdd,
                },
              },
            });
          },
        }),
      ],
    }),
  ],
});
