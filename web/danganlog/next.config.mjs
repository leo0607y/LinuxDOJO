/** 完全な静的書き出し。サーバー実行・画像最適化・API は使わない。 */
const nextConfig = {
  output: 'export',
  distDir: process.env.DANGAN_DIST || '.next',
  images: { unoptimized: true },
  trailingSlash: true,
  reactStrictMode: true,
  poweredByHeader: false
};
export default nextConfig;
