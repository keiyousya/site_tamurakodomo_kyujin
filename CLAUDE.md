# たむらこどもクリニック 看護師募集サイト

## プロジェクト概要
群馬県前橋市のたむらこどもクリニックの看護師（正看護師・准看護師）募集ランディングページ。
Google リスティング広告からの流入を想定した単一ページサイト。

## 技術スタック
- **フレームワーク**: Astro 7.x（静的サイト生成）
- **スタイリング**: Tailwind CSS v4（@theme によるデザイントークン）
- **パッケージマネージャ**: pnpm
- **ホスティング**: GitHub Pages（GitHub Actions でビルド・デプロイ）
- **フォント**: Zen Maru Gothic（Google Fonts CDN、非ブロッキング読み込み）

## コマンド
- `pnpm dev` — 開発サーバー起動
- `pnpm build` — 本番ビルド（dist/ に出力）
- `pnpm preview` — ビルド結果のプレビュー

## ディレクトリ構成
```
src/
├── layouts/Layout.astro    — 共通レイアウト（SEO、OGP、構造化データ）
├── pages/index.astro       — メインページ
├── components/
│   ├── Header.astro        — 固定ヘッダー
│   ├── Footer.astro        — フッター
│   ├── SectionHeading.astro — セクション見出し
│   ├── FeatureCard.astro   — 魅力カード
│   └── RequirementsTable.astro — 募集要項テーブル
└── styles/global.css       — テーマトークン＋ベーススタイル
```

## デザインテーマ
- **Sky**: 水色系（小児科の清潔感・安心感）
- **Leaf**: グリーン系（自然・癒やし）
- **Warm**: オレンジ系（CTAボタン）
- **Cloud**: 白〜ライトグレー（背景）
- **Ink**: ダークグレー（テキスト）

## Google Ads 管理

`ads/` の `gads` CLI（Python・勾当台夕方内科クリニックの `ads/` と同じ作り）で操作する。
セットアップと全コマンドは `ads/README.md` を参照。

- 実行は `ads/.venv/bin/gads`。認証情報は `ads/.env`（コミットしない）
- 広告アカウントは `853-224-9376`（MCC 配下にリンクされていない単独アカウント。login-customer-id も同じID）。
  開発者トークン・OAuth クライアントは web-production と共通で、
  `ads/scripts/pull_secrets.sh` が Secret Manager（keiyousya-sites-prod）から `.env` を作る
- `ads/config.json` がキャンペーン設定。初回構築は `gads setup`（PAUSED で一括作成）
- 作成後の変更は個別コマンドで行い、`config.json` も合わせて更新して現状の控えにする
- 広告文は**サイトの募集要項と一致させる**（パート・14:00〜18:30・週2〜4日・時給1,600円〜）。
  サイトにない条件（正社員・社会保険など）を書かない
- 見出しは全角15字・説明文は全角45字まで（Google は全角を2と数える）
- 変更系コマンドは確認プロンプトが出る。お金が動く操作（ENABLED・予算変更）は実行前にユーザーに確認する
- レポート確認は `--csv` を付ける（表形式は列が省略される）
