/** @type {import('next').NextConfig} */
const nextConfig = {
  serverExternalPackages: ['exceljs', 'cheerio'],
  // data/*.json is read with fs at runtime. Next only traces static imports,
  // so without this the files are missing from Vercel's serverless bundles.
  outputFileTracingIncludes: {
    '/api/**': ['./data/**/*.json'],
  },
};
export default nextConfig;
