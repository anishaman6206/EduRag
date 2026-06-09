/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 'standalone' produces a minimal .next/standalone build that
  // the Dockerfile can copy into a small runtime image (~50MB).
  output: "standalone",
  // Allow the frontend to talk to the FastAPI backend running on
  // a different port. The actual call goes through our /api
  // proxy (rewrites below) so the browser never sees a CORS
  // preflight in production.
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      { source: "/api/backend/:path*", destination: `${backend}/:path*` },
    ];
  },
};

export default nextConfig;
