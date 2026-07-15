import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { resolve } from "node:path";

const source = resolve("apps/web/dist");
const target = resolve("dist");
const hostingManifest = resolve(".openai/hosting.json");

if (!existsSync(source)) {
  throw new Error(`Static export not found: ${source}`);
}

rmSync(target, { recursive: true, force: true });
cpSync(source, target, { recursive: true });

mkdirSync(resolve(target, ".openai"), { recursive: true });
cpSync(hostingManifest, resolve(target, ".openai/hosting.json"));
