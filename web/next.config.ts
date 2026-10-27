import type { NextConfig } from "next";

const nodeApiUrl = (process.env.NODE_API_URL ?? "http://127.0.0.1:3001").replace(
  /\/$/,
  "",
);

const nextConfig: NextConfig = {
  eslint: { ignoreDuringBuilds: true },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${nodeApiUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
