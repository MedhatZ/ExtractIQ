import { createApp } from "./app.js";
import { config } from "./config.js";

const app = createApp();

app.listen(config.port, "127.0.0.1", () => {
  process.stdout.write(`API listening on http://127.0.0.1:${config.port}\n`);
});
