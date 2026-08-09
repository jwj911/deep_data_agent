/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  devIndicators: false,
  experimental: {
    serverActions: {
      bodySizeLimit: "10mb",
    },
  },
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  basePath: "/data_copilot",
  skipTrailingSlashRedirect: true,
};

export default nextConfig;
