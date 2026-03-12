import "dotenv/config";
import * as readline from "node:readline/promises";
import { ToolLoopAgent, stepCountIs } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { createBashTool, CreateBashToolOptions } from "bash-tool";
import { Bash, OverlayFs } from "just-bash";

const overlay = new OverlayFs({ root: process.cwd() });
const mountPoint = overlay.getMountPoint();

const sandbox = new Bash({
    python: true,
    // javascript: true, // enable when released
    executionLimits: {
        maxLoopIterations: 50000,
        maxCommandCount: 20000,
    },
    fs: overlay,
    cwd: overlay.getMountPoint(),
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

// create readline interface for user input
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
});

// system prompt for the agent
const SYSTEM = `
You are OpenClaw, an autonomous Linux engineer running inside a secure justbash sandbox.
The user's project files are located at ${mountPoint}. This is your working directory.

RULES:
1. Your working directory is ${mountPoint} — this is where all the user's files are.
2. Use bash to do ALL tasks: write files, run code, install packages, chain commands.
3. After writing any script, ALWAYS immediately run it using the bash tool.
4. If something fails, read the error and self-correct. Try a different approach.
5. If you need a library or tool, try to install it or write a workaround.
6. Think step by step. Break big tasks into small shell commands.
7. You MUST always write a final text response after finishing all steps. Never end on a tool call.
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
    console.log("SafeClaw ready. Type 'exit' to quit or '/print-bash' to toggle bash output.\n");

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

        process.stdout.write("\nSafeClaw: Thinking...");

        try {
            const result = await agent.generate({
                prompt: userInput,
            });

            console.log(`\nSafeClaw: ${result.text}\n`);

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

/*
Create a Python script called analyze.py that generates a list of 10 random numbers, calculates their average, and saves that average into a new file called result.txt. Then, read result.txt and tell me what the final number is.
*/