#!/usr/bin/env tsx

import "dotenv/config";
import * as readline from "node:readline/promises";
import { ToolLoopAgent, stepCountIs } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { createBashTool } from "bash-tool";
import { Bash, OverlayFs, ReadWriteFs, MountableFs, InMemoryFs } from "just-bash";
import { mkdirSync } from "fs";
import { type ModelMessage } from "ai";
import { setup } from "./env-setup.js";

await setup();

mkdirSync(process.env.OUTPUT_DIR ?? "./output", { recursive: true });

const projectFs = new OverlayFs({ root: process.cwd() });
const outputFs = new ReadWriteFs({ root: process.env.OUTPUT_DIR ?? "./output" });
const mountPoint = projectFs.getMountPoint();

const fs = new MountableFs({ base: new InMemoryFs() });
fs.mount(mountPoint, projectFs);
fs.mount("/home/user/output", outputFs);

const sandbox = new Bash({
    python: true,
    // javascript: true, // enable when released
    executionLimits: {
        maxLoopIterations: 50000,
        maxCommandCount: 20000,
    },
    fs,
    cwd: mountPoint,
    network: {
        allowedUrlPrefixes: ["https://api.github.com/", "https://pypi.org/"],
    },
});

let verbose = process.argv.includes("--print-bash");

const { tools } = await createBashTool({
    sandbox,
    destination: mountPoint,
    onBeforeBashCall: ({ command }) => {
        if (verbose) console.log(`\n  $ ${command}`);
    },
    onAfterBashCall: ({ command, result }) => {
        if (verbose) console.log(`  exit: ${result.exitCode}`);
    },
});

const messages: ModelMessage[] = [];

// create readline interface for user input
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
});

// system prompt for the agent
const SYSTEM = `
You are OpenClaw, an autonomous Linux engineer running inside a secure justbash sandbox.
The user's project files are located at ${mountPoint}. This is your working directory.

IMPORTANT: The output directory is /home/user/output. This is a real directory that exists right now. Always write files here when the user asks to save anything.

RULES:
1. Your working directory is ${mountPoint} — this is where all the user's files are.
2. ALWAYS write output files to /home/user/output — never create an output folder yourself, it already exists at /home/user/output.
3. Use bash to do ALL tasks: write files, run code, install packages, chain commands.
4. After writing any script, ALWAYS immediately run it using the bash tool.
5. If something fails, read the error and self-correct. Try a different approach.
6. If you need a library or tool, try to install it or write a workaround.
7. Think step by step. Break big tasks into small shell commands.
8. You MUST always write a final text response after finishing all steps. Never end on a tool call.
`;

// create agent
const agent = new ToolLoopAgent({
    model: anthropic("claude-sonnet-4-6"),
    tools,
    stopWhen: stepCountIs(20),
    system: SYSTEM,
});

// handle ctrl+c gracefully
process.on("SIGINT", () => {
    rl.close();
    process.exit(0);
});

async function main() {
    console.log("SafeClaw ready. Type 'exit' or use Ctrl+C to quit. Type '/print-bash' to toggle bash output or '/reset' to reset the conversation.\n");

    while (true) {
        let userInput: String;

        try {
            userInput = await rl.question("You: ");
        } catch {
            process.exit(0);
        }

        if (userInput.toLowerCase() === "exit") {
            break;
        }

        if (!userInput.trim()) continue;

        if (userInput === "/print-bash") {
            verbose = !verbose;
            console.log(`Bash output ${verbose ? "shown" : "not shown"}`);
            continue;
        }

        if (userInput === "/reset") {
            messages.length = 0;
            console.log("Conversation reset.");
            continue;
        }

        process.stdout.write("\nSafeClaw: Thinking...");

        try {
            messages.push({ role: "user", content: userInput });
            const result = await agent.generate({ prompt: messages });
            messages.push({ role: "assistant", content: result.text });

            console.log(`\nSafeClaw: ${result.text}\n`);

            // for debugging:
            // console.log("result keys:", Object.keys(result));
            // console.log("result.text:", JSON.stringify(result.text));
            // console.log("steps:", (result as any).steps?.length);
            // console.log("full result:", JSON.stringify(result, null, 2).slice(0, 1000));

        } catch (error) {
            console.error("\nError:", error);
        }
    }

    rl.close();
}

main();
