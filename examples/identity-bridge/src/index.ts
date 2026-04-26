import express from "express";
import cors from "cors";
import { PORT } from "./config";
import authRoutes from "./routes/auth";
import healthRoutes from "./routes/health";

const app = express();
app.use(cors());
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

app.use("/auth", authRoutes);
app.use("/", healthRoutes);

// Root redirects to login
app.get("/", (_req, res) => res.redirect("/auth/login"));

app.listen(PORT, () => {
  console.log(`Identity Bridge Example running on http://localhost:${PORT}`);
  console.log(`Open http://localhost:${PORT}/auth/login to start`);
});

export default app;
