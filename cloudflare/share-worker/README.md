# Aiko Share Worker

1. Create a private R2 bucket named `private-shares` (or update `wrangler.toml`).
2. Keep `r2.dev` and public custom-domain access disabled for this bucket.
3. Run `npx wrangler deploy` from this directory.
4. Put the deployed Worker URL into **Settings > Chia sẻ > Đường dẫn Share Worker**.

The local app uploads manifests and chapter objects with its private R2 credentials. Opening a share link displays the built-in reader; it fetches the authenticated manifest first and one chapter only when selected. The URL token is moved into browser session storage and removed from the address bar. R2 receives only its SHA-256 hash.
