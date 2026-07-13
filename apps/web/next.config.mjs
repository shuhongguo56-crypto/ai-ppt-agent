const pagesRepo = process.env.GITHUB_PAGES_REPO?.trim();
const isGithubPages = Boolean(pagesRepo);
const basePath = isGithubPages ? `/${pagesRepo}` : "";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  basePath,
  assetPrefix: isGithubPages ? `${basePath}/` : undefined,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
