/** @type {import('next').NextConfig} */
const isProd = process.env.NODE_ENV === 'production';

const nextConfig = {
  ...(isProd && { output: 'export' }),
  devIndicators: false,
  experimental: {
    serverActions: {
      bodySizeLimit: "10mb",
    },
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  trailingSlash: true,
  images: {
    unoptimized: isProd
  },
  ...(isProd && { basePath: '/data_copilot' }),
  skipTrailingSlashRedirect: true,
  typescript: {
    ignoreBuildErrors: true
  }
};

export default nextConfig;
