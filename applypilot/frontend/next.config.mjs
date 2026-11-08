/** @type {import('next').NextConfig} */
const backend = (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");
const backendUrl = /^https?:\/\//.test(backend) ? backend : `http://${backend}`;

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // AI analysis and CV parsing can take a while; don't cut proxied requests off early.
  experimental: { proxyTimeout: 300000 },
  // Same-origin API: the browser calls /api/*, Next.js forwards to the FastAPI backend.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
  async headers() {
    return [{
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      ],
    }];
  },
};
export default nextConfig;
