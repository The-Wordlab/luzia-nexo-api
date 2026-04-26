import { Router, Request, Response } from "express";
import { isValidE164, normalizePhone } from "../lib/phone";
import { createOtp, verifyOtp } from "../lib/otp-store";
import { NexoIdentityBridgeClient } from "../nexo-client";
import { readFileSync } from "fs";
import { join } from "path";

const router = Router();
const nexo = new NexoIdentityBridgeClient();

function renderView(name: string, vars: Record<string, string> = {}): string {
  let html = readFileSync(
    join(__dirname, "..", "views", `${name}.html`),
    "utf-8",
  );
  for (const [key, value] of Object.entries(vars)) {
    html = html.replace(new RegExp(`\\{\\{${key}\\}\\}`, "g"), value);
  }
  return html;
}

// GET /auth/login - show phone input form
router.get("/login", (_req: Request, res: Response) => {
  res.type("html").send(renderView("login", { error: "" }));
});

// POST /auth/request-code - validate phone, create OTP
router.post("/request-code", (req: Request, res: Response) => {
  const phone = normalizePhone(req.body?.phone || "");
  if (!isValidE164(phone)) {
    res
      .type("html")
      .send(
        renderView("login", {
          error:
            '<p class="error">Invalid phone number. Use international format: +34612345678</p>',
        }),
      );
    return;
  }
  const code = createOtp(phone);
  console.log(`[OTP] Code for ${phone}: ${code}`);
  res.type("html").send(renderView("verify", { phone, error: "" }));
});

// POST /auth/verify-code - verify OTP, call Nexo link-start
router.post("/verify-code", async (req: Request, res: Response) => {
  const phone = req.body?.phone || "";
  const code = req.body?.code || "";

  if (!verifyOtp(phone, code)) {
    res
      .type("html")
      .send(
        renderView("verify", {
          phone,
          error:
            '<p class="error">Invalid or expired code. Try again.</p>',
        }),
      );
    return;
  }

  try {
    // Generate a stable partner user ID from the phone
    const externalUserId = `partner-${phone.replace("+", "")}`;

    const result = await nexo.linkStart(phone, externalUserId, {
      display_name: `User ${phone.slice(-4)}`,
      locale: "en",
    });

    if (result.link_status === "confirm_required") {
      res
        .type("html")
        .send(
          renderView("verify", {
            phone,
            error: `<p class="error">This phone is already linked to a Nexo account (${result.existing_user_hint || "unknown"}). Confirmation flow not yet implemented in this demo.</p>`,
          }),
        );
      return;
    }

    // Success - show linked state
    res.type("html").send(
      renderView("linked", {
        nexo_user_id: result.nexo_user_id || "unknown",
        link_status: result.link_status,
        phone,
        external_user_id: externalUserId,
        token_preview: result.access_token
          ? result.access_token.slice(0, 20) + "..."
          : "none",
      }),
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error";
    res
      .type("html")
      .send(
        renderView("verify", {
          phone,
          error: `<p class="error">Nexo bridge error: ${msg}</p>`,
        }),
      );
  }
});

export default router;
