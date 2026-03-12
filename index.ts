import "dotenv/config";
import * as readline from "node:readline/promises";
import { ToolLoopAgent, stepCountIs } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { createBashTool } from "bash-tool";
import { Bash } from "just-bash";

const sandbox = new Bash({ python: true });
const { tools } = await createBashTool({ sandbox});

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
});

const SYSTEM = `
You are OpenClaw, an autonomous Linux engineer running inside a secure justbash sandbox.

RULES:
1. You have a full Ubuntu-like filesystem in memory — use it freely.
2. Use bash to do ALL tasks: write files, run code, install packages, chain commands.
3. After writing any script, ALWAYS immediately run it using the bash tool.
4. If something fails, read the error and self-correct. Try a different approach.
5. If you need a library or tool, try to install it or write a workaround.
6. Think step by step. Break big tasks into small shell commands.
7. You MUST always write a final text response after finishing all steps. Never end on a tool call.
`;

const agent = new ToolLoopAgent({
    model: anthropic("claude-sonnet-4-6"),
    tools,
    stopWhen: stepCountIs(20),
    system: SYSTEM,
});

async function main() {
    console.log("SafeClaw ready. Type 'exit' to quit.\n");

    while (true) {
        const userInput = await rl.question("You: ");

        if (userInput.toLowerCase() === "exit") {
            console.log("Goodbye.");
            break;
        }

        if (!userInput.trim()) continue;

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