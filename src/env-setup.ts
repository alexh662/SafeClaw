import { config } from "dotenv";
import { join } from "path";
import { existsSync, writeFileSync } from "fs";
import * as readline from "node:readline/promises";

export const localEnv = join(process.cwd(), ".env");
export const globalEnv = join(process.env.HOME ?? "~", ".safeclaw.env");

config({ path: localEnv });
config({ path: globalEnv });

export const ENV_PATH = existsSync(localEnv) ? localEnv : globalEnv;

export async function setup() {
    const hasKey = process.env.ANTHROPIC_API_KEY?.trim();
    const hasDir = process.env.OUTPUT_DIR?.trim();

    if (hasKey && hasDir) return;

    console.log("SafeClaw first-time setup\n");

    const setupRl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
    });

    let anthropicKey = process.env.ANTHROPIC_API_KEY?.trim() ?? "";
    let outputDir = process.env.OUTPUT_DIR?.trim() ?? "";

    if (!anthropicKey) {
        anthropicKey = (await setupRl.question("Enter your Anthropic API key: ")).trim();
    }

    if (!outputDir) {
        const defaultDir = join(process.env.HOME ?? "~", "safeclaw-output");
        const input = await setupRl.question(`Enter output directory (default: ${defaultDir}): `);
        outputDir = input.trim() || defaultDir;
    }

    setupRl.close();

    process.env.ANTHROPIC_API_KEY = anthropicKey;
    process.env.OUTPUT_DIR = outputDir;

    writeFileSync(ENV_PATH, `ANTHROPIC_API_KEY=${anthropicKey}\nOUTPUT_DIR=${outputDir}\n`);

    console.log(`\nConfig saved to ${ENV_PATH}\n`);
}
