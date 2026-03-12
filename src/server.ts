import { Hono } from "hono";
import { serve } from "@hono/node-server";
import { setup } from "./env-setup.js";
import { runAgent } from "./agent.js";

await setup();

const app = new Hono();

app.post("/run", async (c) => {
    const { task, system } = await c.req.json();

    if (!task) {
        return c.json({ success: false, error: "task is required" }, 400);
    }

    try {
        const response = await runAgent(task, system);
        return c.json({ success: true, response });
    } catch (error) {
        return c.json({ success: false, error: String(error) }, 500);
    }
});

const PORT = Number(process.env.PORT) || 3000;

serve({ fetch: app.fetch, port: PORT }, () => {
    console.log(`SafeClaw server running on http://localhost:${PORT}`);
});
