import type { HTMLAttributes } from "react";

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "dotlottie-wc": HTMLAttributes<HTMLElement> & {
        src: string;
        autoplay?: string;
        loop?: string;
      };
    }
  }
}
