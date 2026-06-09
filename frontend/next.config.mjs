/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow the frontend to talk to the FastAPI backend running on
  // a different port in dev. The actual call goes through our
  // /api proxy (rewrites below) so the browser never sees a CORS
  // preflight in production.
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      { source: "/api/backend/:path*", destination: `${backend}/:path*` },
    ];
  },
};

export default nextConfig;
