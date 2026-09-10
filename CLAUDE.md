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

### 概要
Google Ads APIをCLIから操作してリスティング広告を管理する。
Claude AIエージェントが広告の作成・更新・レポート取得を支援する。

### セットアップ手順

1. **Google Ads API アクセス設定**
   ```bash
   # Google Ads API の開発者トークンを取得
   # https://developers.google.com/google-ads/api/docs/get-started/dev-token

   # google-ads.yaml に認証情報を設定
   cat > google-ads.yaml << 'EOF'
   developer_token: "YOUR_DEVELOPER_TOKEN"
   client_id: "YOUR_CLIENT_ID"
   client_secret: "YOUR_CLIENT_SECRET"
   refresh_token: "YOUR_REFRESH_TOKEN"
   login_customer_id: "YOUR_MANAGER_ACCOUNT_ID"
   EOF
   ```

2. **Python クライアントライブラリのインストール**
   ```bash
   pip install google-ads
   ```

3. **Google Ads アカウントの作成**
   - https://ads.google.com でアカウントを作成
   - API アクセスを有効化

### Claude AI エージェントによる広告管理

以下のタスクをClaude Codeに依頼できる：

#### キャンペーン管理
- `ads/` ディレクトリ内のスクリプトでキャンペーンを管理
- キャンペーン作成・予算変更・ステータス変更

#### 広告文の管理
- 広告文のA/Bテスト案作成
- レスポンシブ検索広告のアセット（見出し・説明文）管理

#### キーワード管理
- ターゲットキーワードの提案・追加・除外
- 推奨キーワード例：
  - `看護師 求人 前橋`
  - `看護師 募集 群馬`
  - `小児科 看護師 求人`
  - `准看護師 パート 前橋市`
  - `看護師 転職 群馬県`
  - `クリニック 看護師 日勤のみ`

#### レポート
- クリック数・表示回数・コンバージョンのレポート取得
- パフォーマンス分析と改善提案

### 広告設定ファイル（ads/config.json）
広告の設定をJSON形式で管理し、スクリプトで Google Ads API に反映する。
