/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',  // 添加这一行
  devIndicators: false,
  experimental: {
    serverActions: {
      bodySizeLimit: "10mb",
    },
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  // 可选：确保静态资源路径正确
  trailingSlash: true,
  images: {
    unoptimized: true  // 静态导出时需要这个配置
  },
  basePath: '/data_copilot',
  // 添加这个配置来跳过 API 路由
  skipTrailingSlashRedirect: true,
  // 确保静态导出时忽略动态路由
  typescript: {
    ignoreBuildErrors: true,
  }
};

export default nextConfig;
