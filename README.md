# YimmParking

輸入台北／新北的地址，列出附近的停車場：嘟嘟房、台灣聯通優先，嘟嘟房若在 iParking 清單內排最前；顯示即時空位與資料時間；選一個停車場後，看它周圍 1 公里的美食。

- `backend/` Python 後端（乾淨架構：domain → application → adapters → interface），詳見 [backend/README.md](backend/README.md)。
- `web/` TypeScript 前端（Vite + React），型別由後端 OpenAPI 產生。
- `PRODUCT.md`、`DESIGN.md` 產品與視覺系統（impeccable 流程產物）。

## 本機執行

```bash
# 後端（先在 backend/.env 填 GOOGLE_MAPS_API_KEY，才有「地址搜尋」與「美食」）
cd backend
.venv/Scripts/python -m yimmparking.interface.cli refresh-lots --yes
.venv/Scripts/python -m yimmparking.interface.cli worker            # 持續更新即時空位
.venv/Scripts/python -m yimmparking.interface.cli serve --port 49387

# 前端（開發伺服器會把 /api 代理到後端）
cd web
pnpm install
pnpm dev
```

沒有 Google 金鑰時：地址搜尋回 503、美食顯示「尚未設定」，用座標查詢
（`/?lat=25.0375&lng=121.5637`）或「使用目前位置」仍可使用。

## 對外服務（WSL + Cloudflare Tunnel）

`parking.yimmhub.com` 由 WSL 裡的 cloudflared 轉到 `http://localhost:5173`，這個 `localhost`
指的是 **WSL**，所以服務必須在 WSL 內執行（Windows 上的程序它連不到，會是 502）。

服務使用的程式碼就是 WSL 裡的 checkout（預設 `~/projects/YimmParking`，可用 `YIMM_SRC` 改），
不要再指到 `/mnt/d/...`。

```bash
cd ~/projects/YimmParking/web && pnpm install --frozen-lockfile && pnpm build   # 在 WSL 建置，產生 web/dist
bash ~/projects/YimmParking/deploy/wsl-setup.sh   # 建 venv、（必要時）複製 DB、寫入並啟動兩個 user service
```

- `yimmparking-api`：同一個程序提供 API 與已建置的前端，監聽 `127.0.0.1:5173`。
- `yimmparking-worker`：持續更新停車場與即時空位。
- 資料庫在 WSL 的 `~/yimmparking/data/yimmparking.db`（與 Windows 上 `backend/data` 是兩份）。
- 改了後端程式：`systemctl --user restart yimmparking-api yimmparking-worker`。
- 改了前端：重新 `pnpm build` 即可（靜態檔，不必重啟）。
- 本機開發前端用 `pnpm dev`（埠 5174，會代理 `/api` 到後端）。
