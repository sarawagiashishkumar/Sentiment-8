import express from "express";
import { generateText } from "ai";

const app = express();
app.use(express.json({ limit: "24kb" }));

app.post("/generate", async (request, response) => {
  const { system, prompt } = request.body ?? {};
  if (
    typeof system !== "string" ||
    typeof prompt !== "string" ||
    system.length > 12_000 ||
    prompt.length > 8_000
  ) {
    return response.status(400).json({ error: "Invalid AI support request." });
  }

  try {
    const result = await generateText({
      model: "openai/gpt-5.4-mini",
      system,
      prompt,
      maxOutputTokens: 350,
      timeout: 45_000,
    });

    return response.json({ text: result.text });
  } catch {
    console.error("[ai-service] AI Gateway request failed");
    return response.status(502).json({ error: "AI support is temporarily unavailable." });
  }
});

export default app;
