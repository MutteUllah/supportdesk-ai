import { cp, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
const standalone = join(root, ".next", "standalone");
await mkdir(join(standalone, ".next"), { recursive: true });
await cp(join(root, ".next", "static"), join(standalone, ".next", "static"), {
  recursive: true,
});
await cp(join(root, "public"), join(standalone, "public"), { recursive: true });
process.env.HOSTNAME ||= "127.0.0.1";
process.env.PORT ||= "3000";
await import(new URL("../.next/standalone/server.js", import.meta.url));
