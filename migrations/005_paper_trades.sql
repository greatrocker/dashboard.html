-- ==================================================================
-- 套利模擬交易（paper trading）
-- 每筆強力買訊號：現貨端買入現貨、合約端放空合約（數量 = 可套利幣量，以即時訂單簿逐檔成交）
-- 平倉：扣手續費後損益 >= 停利門檻，或 Open Gap 回到開倉時的 5 分鐘均值
-- 可重複執行
-- ==================================================================

USE [Crypto];
GO

IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[PaperTrades]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[PaperTrades] (
        [Id]                 BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        [SignalId]           BIGINT          NULL,       -- 對應 StrongBuySignals.Id
        [Symbol]             NVARCHAR(50)    NOT NULL,
        [BaseExchange]       NVARCHAR(20)    NOT NULL,   -- 買現貨
        [TargetExchange]     NVARCHAR(20)    NOT NULL,   -- 放空合約
        [Status]             NVARCHAR(10)    NOT NULL,   -- OPEN / CLOSED
        [Qty]                DECIMAL(28, 10) NOT NULL,   -- 幣量（兩邊相同）
        [OpenedAt]           DATETIME        NOT NULL CONSTRAINT [DF_PaperTrades_OpenedAt] DEFAULT (GETDATE()),
        [EntrySpotPrice]     DECIMAL(28, 10) NOT NULL,   -- 買現貨成交均價
        [EntryContractPrice] DECIMAL(28, 10) NOT NULL,   -- 放空合約成交均價
        [EntryOpenGap]       DECIMAL(18, 8)  NOT NULL,   -- 實際成交的 Open Gap %
        [EntryAvgOpenGap]    DECIMAL(18, 8)  NOT NULL,   -- 開倉時的 5 分鐘均值（均值回歸平倉用）
        [EntryFee]           DECIMAL(18, 6)  NOT NULL,   -- USDT
        [CostUsd]            DECIMAL(18, 2)  NOT NULL,   -- 買現貨花費（報酬率分母）
        -- 持倉中：每 10 秒更新一次的即時估值（以最新買賣價、未含平倉滑價）
        [MarkTime]           DATETIME        NULL,
        [MarkSpotBid]        DECIMAL(28, 10) NULL,
        [MarkContractAsk]    DECIMAL(28, 10) NULL,
        [UnrealizedPnl]      DECIMAL(18, 6)  NULL,
        [UnrealizedPct]      DECIMAL(18, 6)  NULL,
        -- 平倉後
        [ClosedAt]           DATETIME        NULL,
        [ExitReason]         NVARCHAR(20)    NULL,       -- TAKE_PROFIT / MEAN_REVERT
        [ExitSpotPrice]      DECIMAL(28, 10) NULL,       -- 賣現貨成交均價
        [ExitContractPrice]  DECIMAL(28, 10) NULL,       -- 買回合約成交均價
        [ExitFee]            DECIMAL(18, 6)  NULL,
        [GrossPnl]           DECIMAL(18, 6)  NULL,       -- 未扣手續費
        [NetPnl]             DECIMAL(18, 6)  NULL,       -- 扣除 4 筆手續費
        [NetPnlPct]          DECIMAL(18, 6)  NULL,       -- NetPnl / CostUsd * 100
        [ExitFillSource]     NVARCHAR(10)    NULL        -- BOOK：即時訂單簿逐檔成交；QUOTE：訂單簿失敗改用最新報價
    );
    CREATE INDEX [IX_PaperTrades_Status] ON [dbo].[PaperTrades] ([Status], [OpenedAt] DESC);
    CREATE INDEX [IX_PaperTrades_ClosedAt] ON [dbo].[PaperTrades] ([ClosedAt] DESC);
END
GO

PRINT 'PaperTrades is ready.';
GO
