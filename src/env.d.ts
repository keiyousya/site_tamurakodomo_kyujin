// Google 広告の gtag.js（Layout.astro で読み込む）
interface Window {
  dataLayer?: unknown[];
  gtag?: (...args: unknown[]) => void;
}
