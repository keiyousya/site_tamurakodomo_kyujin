import { onRequest } from "firebase-functions/v2/https";
import { defineSecret } from "firebase-functions/params";
import * as nodemailer from "nodemailer";

const gmailAppPassword = defineSecret("gmail-app-password");

const GMAIL_AUTH_USER = "tamurakeito@keiyousya.com";
const MAIL_FROM = "tamurakodomo-kyujin@keiyousya.com";
const MAIL_TO = "tamurakeito@keiyousya.com, tamurakodomo@gmail.com";

// インメモリレートリミット
const rateLimitMap = new Map<string, number[]>();
const RATE_LIMIT = 3;
const RATE_WINDOW_MS = 60_000;

export const sendApplyEmail = onRequest(
  {
    region: "asia-northeast1",
    secrets: [gmailAppPassword],
    serviceAccount:
      "cf-contact-form@keiyousya-sites-prod.iam.gserviceaccount.com",
    maxInstances: 10,
    invoker: "public",
  },
  async (req, res) => {
    if (req.method !== "POST") {
      res.status(405).json({ error: "Method not allowed" });
      return;
    }

    // レートリミット
    const ip = req.ip || "unknown";
    const now = Date.now();
    const timestamps = (rateLimitMap.get(ip) || []).filter(
      (t) => now - t < RATE_WINDOW_MS
    );
    if (timestamps.length >= RATE_LIMIT) {
      res
        .status(429)
        .json({
          error: "送信回数の上限に達しました。しばらくしてからお試しください。",
        });
      return;
    }
    timestamps.push(now);
    rateLimitMap.set(ip, timestamps);

    const { name, age, license, email, phone, message, _hp } = req.body;

    // ハニーポット
    if (_hp) {
      res.status(200).json({ success: true });
      return;
    }

    // バリデーション
    if (!name || !email) {
      res
        .status(400)
        .json({ error: "お名前・メールアドレスを入力してください。" });
      return;
    }

    if (typeof name !== "string" || name.length > 100) {
      res
        .status(400)
        .json({ error: "お名前は100文字以内で入力してください。" });
      return;
    }

    if (
      typeof email !== "string" ||
      email.length > 254 ||
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
    ) {
      res.status(400).json({ error: "有効なメールアドレスを入力してください。" });
      return;
    }

    if (phone && (typeof phone !== "string" || phone.length > 20)) {
      res
        .status(400)
        .json({ error: "電話番号は20文字以内で入力してください。" });
      return;
    }

    if (message && (typeof message !== "string" || message.length > 5000)) {
      res
        .status(400)
        .json({ error: "メッセージは5000文字以内で入力してください。" });
      return;
    }

    try {
      const transporter = nodemailer.createTransport({
        service: "gmail",
        auth: {
          user: GMAIL_AUTH_USER,
          pass: gmailAppPassword.value(),
        },
      });

      await transporter.sendMail({
        from: `"たむらこどもクリニック 採用窓口" <${MAIL_FROM}>`,
        to: MAIL_TO,
        replyTo: email,
        subject: `【看護師応募】${name}様より`,
        text: [
          `お名前: ${name}`,
          `年齢: ${age || "未入力"}`,
          `保有資格: ${license || "未入力"}`,
          `メールアドレス: ${email}`,
          `電話番号: ${phone || "未入力"}`,
          "",
          "メッセージ:",
          message || "未入力",
        ].join("\n"),
      });

      res.status(200).json({ success: true });
    } catch (error) {
      console.error("Failed to send email:", error);
      res
        .status(500)
        .json({ error: "送信に失敗しました。しばらくしてからお試しください。" });
    }
  }
);
