/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 路径分流部署在 /freedom
  basePath: '/freedom',
  assetPrefix: '/freedom',
  trailingSlash: true,
};

module.exports = nextConfig;
