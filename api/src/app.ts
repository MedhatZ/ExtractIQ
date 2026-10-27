import express from "express";

import { AppError, errorBody } from "./errors.js";
import { callExtractor } from "./extractorClient.js";
import { validateExtractInput } from "./validate.js";

export function createApp(deps: { callExtractor?: typeof callExtractor } = {}) {
  const extract = deps.callExtractor ?? callExtractor;
  const app = express();
  app.use(express.json({ limit: "32kb" }));

  app.get("/health", (_req, res) => {
    res.json({ status: "ok" });
  });

  app.post("/extract", async (req, res, next) => {
    try {
      const { url } = validateExtractInput(req.body);
      const result = await extract(url);
      res.json(result);
    } catch (error) {
      next(error);
    }
  });

  app.use(
    (
      error: unknown,
      _req: express.Request,
      res: express.Response,
      _next: express.NextFunction,
    ) => {
      if (error instanceof AppError) {
        res.status(error.status).json(errorBody(error.code, error.message));
        return;
      }
      res.status(500).json(errorBody("INTERNAL_ERROR", "unexpected server error"));
    },
  );

  return app;
}
