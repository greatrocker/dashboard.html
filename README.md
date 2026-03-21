# 多交易所市場監控系統 - 完整版

**特色：前端下拉選單切換交易所，無需重啟容器**

## 📦 專案結構

```
exchange-monitor-complete/
├── api_server.py           ← FastAPI 後端（支援多交易所查詢）
├── config.py               ← 交易所配置檔
├── bybit_ticker.py         ← Bybit WebSocket Ticker
├── static/
│   └── dashboard.html      ← 前端 Dashboard（含交易所切換器）
├── docker-compose.yml      ← 容器編排（API + Ticker + Uptime Kuma）
├── Dockerfile
├── requirements.txt        ← Python 依賴
├── .env.example            ← 環境變數範例
└── README.md
```

---

## 🚀 快速開始

### 1. 設定環境變數

```bash
cp .env.example .env
nano .env
```

修改 MSSQL 密碼和 Telegram 設定（選填）。

### 2. 建立 MSSQL Tables

#### Bybit Table

```sql
CREATE TABLE [dbo].[Bybit] (
    [Time] DATETIME NOT NULL,
    [Symbol] NVARCHAR(50) NOT NULL,
    [Spot_bids] DECIMAL(18, 8),
    [Spot_asks] DECIMAL(18, 8),
    [Contract_bids] DECIMAL(18, 8),
    [Contract_asks] DECIMAL(18, 8),
    [Open_position_Gap] DECIMAL(18, 8),
    [Close_position_Gap] DECIMAL(18, 8),
    [Open_position_Gap2nd] DECIMAL(18, 8),
    [Close_position_Gap2nd] DECIMAL(18, 8),
    PRIMARY KEY ([Time], [Symbol])
);
```

#### Bybit Stored Procedure

```sql
CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_bybit]
    @p_time DATETIME,
    @p_symbol NVARCHAR(50),
    @p_Spot_bids DECIMAL(18, 8) = NULL,
    @p_Spot_asks DECIMAL(18, 8) = NULL,
    @p_Contract_bids DECIMAL(18, 8) = NULL,
    @p_Contract_asks DECIMAL(18, 8) = NULL
AS
BEGIN
    BEGIN TRY
        DECLARE @Open_position_Gap  DECIMAL(18, 8) = NULL;
        DECLARE @Close_position_Gap DECIMAL(18, 8) = NULL;

        IF @p_Spot_asks IS NOT NULL AND @p_Spot_asks <> 0
            SET @Open_position_Gap = (@p_Contract_bids - @p_Spot_asks) / @p_Spot_asks * 100;

        IF @p_Contract_asks IS NOT NULL AND @p_Contract_asks <> 0
            SET @Close_position_Gap = (@p_Spot_bids - @p_Contract_asks) / @p_Contract_asks * 100;

        MERGE INTO dbo.Bybit AS md
        USING (
            SELECT @p_time AS [Time], @p_symbol AS Symbol,
                   @p_Spot_bids AS Spot_bids, @p_Spot_asks AS Spot_asks,
                   @p_Contract_bids AS Contract_bids, @p_Contract_asks AS Contract_asks,
                   @Open_position_Gap AS Open_position_Gap,
                   @Close_position_Gap AS Close_position_Gap,
                   NULL AS Open_position_Gap2nd, NULL AS Close_position_Gap2nd
        ) AS src
        ON (md.[Time] = src.[Time] AND md.Symbol = src.Symbol)
        WHEN MATCHED THEN
            UPDATE SET
                Spot_bids = ISNULL(src.Spot_bids, md.Spot_bids),
                Spot_asks = ISNULL(src.Spot_asks, md.Spot_asks),
                Contract_bids = ISNULL(src.Contract_bids, md.Contract_bids),
                Contract_asks = ISNULL(src.Contract_asks, md.Contract_asks),
                Open_position_Gap = ISNULL(src.Open_position_Gap, md.Open_position_Gap),
                Close_position_Gap = ISNULL(src.Close_position_Gap, md.Close_position_Gap)
        WHEN NOT MATCHED THEN
            INSERT ([Time], Symbol, Spot_bids, Spot_asks, Contract_bids, Contract_asks,
                    Open_position_Gap, Close_position_Gap, Open_position_Gap2nd, Close_position_Gap2nd)
            VALUES (src.[Time], src.Symbol, src.Spot_bids, src.Spot_asks,
                    src.Contract_bids, src.Contract_asks, src.Open_position_Gap,
                    src.Close_position_Gap, src.Open_position_Gap2nd, src.Close_position_Gap2nd);
    END TRY
    BEGIN CATCH
        DECLARE @ErrMsg NVARCHAR(4000);
        SET @ErrMsg = ERROR_MESSAGE();
        RAISERROR('Error in merge_market_data_bybit: %s', 16, 1, @ErrMsg);
    END CATCH
END;
```

### 3. 啟動所有服務

```bash
docker compose up -d --build
```

### 4. 訪問服務

| 服務 | URL | 說明 |
|------|-----|------|
| **Dashboard** | http://localhost:8000 | 主介面，可切換交易所 |
| **API Docs** | http://localhost:8000/docs | FastAPI 自動文檔 |
| **Uptime Kuma** | http://localhost:3001 | 監控管理介面 |

---

## 📊 Dashboard 使用

1. **切換交易所**：頂部下拉選單選擇 Bybit / Binance / OKX
2. **篩選幣種**：選擇特定幣種或全部
3. **查詢範圍**：1分 / 5分 / 15分 / 30分 / 1小時
4. **自動更新**：每 2 秒自動拉取最新資料
5. **搜尋功能**：可搜尋幣種或時間

---

## 🔧 維護指令

```bash
# 查看 log
docker compose logs -f exchange-api
docker compose logs -f bybit-ticker

# 重啟服務
docker compose restart bybit-ticker

# 停止所有服務
docker compose down

# 清理並重建
docker compose down -v
docker compose up -d --build
```

---

## ➕ 新增其他交易所

### 步驟 1：在 `api_server.py` 加入配置

```python
EXCHANGES = {
    "bybit": {...},
    "binance": {
        "name": "Binance",
        "display_name": "Binance Market Monitor",
        "db_table": "Binance"
    },
}
```

### 步驟 2：建立 MSSQL Table 和 SP

複製 Bybit 的 SQL，把名稱改成 Binance。

### 步驟 3：建立 Ticker 檔案

```bash
cp bybit_ticker.py binance_ticker.py
```

修改 WebSocket URL 和訂閱邏輯以符合 Binance API。

### 步驟 4：在 `config.py` 加入配置

```python
"binance": {
    "name": "Binance",
    "db_table": "Binance",
    "sp_name": "merge_market_data_binance",
    "ws_spot_url": "wss://stream.binance.com:9443/ws",
    "ws_contract_url": "wss://fstream.binance.com/ws",
    ...
}
```

### 步驟 5：在 `docker-compose.yml` 加入 Binance Ticker

```yaml
binance-ticker:
  build: .
  container_name: binance-ticker
  restart: unless-stopped
  command: python -u binance_ticker.py
  environment:
    - EXCHANGE=binance
    ...
```

### 步驟 6：重新啟動

```bash
docker compose up -d --build
```

Dashboard 下拉選單會自動出現 Binance 選項！

---

## 📡 API Endpoints

### 取得所有交易所清單

```bash
GET /api/exchanges
```

回應：
```json
{
  "success": true,
  "exchanges": [
    {"id": "bybit", "name": "Bybit", "db_table": "Bybit"},
    {"id": "binance", "name": "Binance", "db_table": "Binance"}
  ]
}
```

### 查詢市場資料

```bash
GET /api/data?exchange=bybit&minutes=5&limit=100&symbol=BTCUSDT
```

參數：
- `exchange`（必填）：交易所 ID
- `minutes`：查詢最近 N 分鐘
- `limit`：最多回傳幾筆
- `symbol`：幣種（可選）

### 查詢幣種清單

```bash
GET /api/symbols?exchange=bybit
```

---

## 🎯 功能特色

- ✅ **前端切換交易所**：下拉選單即時切換，無需重啟
- ✅ **多交易所並行**：每個交易所獨立 Ticker，互不干擾
- ✅ **自動重啟**：Crash 後 Docker 自動重啟
- ✅ **Log 持久化**：掛載到 `./logs/`
- ✅ **斷線重連**：WebSocket 斷線自動重連
- ✅ **Telegram 告警**：重要事件自動通知
- ✅ **Uptime Kuma 監控**：TCP 心跳監控
- ✅ **Gap 自動計算**：SP 自動計算 Open/Close Gap

---

## 📝 注意事項

1. **MSSQL 連線**：確保 MSSQL 允許 Docker 容器連線
2. **Port 衝突**：確保 8000 / 9000 / 3001 未被佔用
3. **Telegram Token**：可選填，不填不影響主功能
4. **幣種清單**：在 `config.py` 的 `SYMBOLS` 修改

---

## 📞 問題排查

### Dashboard 顯示「DB 連線失敗」

1. 檢查 MSSQL 是否運行
2. 檢查 `.env` 的密碼是否正確
3. 檢查防火牆是否允許連線

### Ticker 沒有寫入資料

1. 檢查 SP 是否建立成功
2. 查看 log：`docker compose logs -f bybit-ticker`
3. 確認 WebSocket 是否連線成功

### 切換交易所沒資料

1. 確認該交易所的 Table 已建立
2. 確認該交易所的 Ticker 正在運行
3. 查看 API log：`docker compose logs -f exchange-api`

---

## 📄 授權

MIT License
