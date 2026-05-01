/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // typedRoutes is too strict for dynamic href strings used in nav/dashboard
  // typedRoutes: true,
  allowedDevOrigins: ["192.168.0.144", "localhost", "127.0.0.1"],
};

export default nextConfig;
