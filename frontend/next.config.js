/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 路径分流部署在 /freedom
  basePath: '/freedom',
  assetPrefix: '/freedom',
  trailingSlash: true,
  async rewrites() {
    // 开发时代理 API 请求到后端，避免 CORS
    const apiUrl = process.env.API_PROXY_URL || 'http://localhost:9000';
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/freedom/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
