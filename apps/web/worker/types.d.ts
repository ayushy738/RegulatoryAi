type Fetcher = {
  fetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response>;
};

type D1Database = unknown;

declare module "cloudflare:workers" {
  export const env: {
    DB?: D1Database;
  };
}
