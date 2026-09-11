import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Pin the file-tracing root to the monorepo root (this app has no
  // dependency on sibling workspace packages today, but pinning this
  // avoids Next.js guessing wrong about the workspace root — and the
  // "wrong lockfile detected" warning that comes with it — should that
  // change, since Vercel's serverless bundling for the dynamic routes
  // (/app, /api/news, etc.) relies on accurate file tracing.
  outputFileTracingRoot: path.join(__dirname, "../.."),
};

export default nextConfig;
