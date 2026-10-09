-- ==================================================================
-- 跨交易所「強力買」訊號紀錄
-- Dashboard 跨交易所分頁偵測到 Open Gap 偏離均值 > 0.5% 時寫入一筆
-- 可重複執行
-- ==================================================================

USE [Crypto];
GO

IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[StrongBuySignals]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[StrongBuySignals] (
        [Id]                BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        [DetectedAt]        DATETIME        NOT NULL CONSTRAINT [DF_StrongBuySignals_DetectedAt] DEFAULT (GETDATE()),
        [DataTime]          DATETIME        NOT NULL,   -- 觸發訊號的那一筆行情時間
        [Symbol]            NVARCHAR(50)    NOT NULL,
        [BaseExchange]      NVARCHAR(20)    NOT NULL,   -- 現貨買入端
        [TargetExchange]    NVARCHAR(20)    NOT NULL,   -- 合約賣出端
        [OpenGap]           DECIMAL(18, 8)  NOT NULL,   -- %
        [AvgOpenGap]        DECIMAL(18, 8)  NOT NULL,   -- %
        [Deviation]         DECIMAL(18, 8)  NOT NULL,   -- OpenGap - AvgOpenGap（百分點）
        [BaseSpotAsk]       DECIMAL(18, 8)  NULL,
        [TargetContractBid] DECIMAL(18, 8)  NULL,
        [WindowMinutes]     INT             NOT NULL,   -- 均值計算區間
        -- 多個瀏覽器同時開著時，同一筆行情只記一次
        CONSTRAINT [UQ_StrongBuySignals_Event] UNIQUE ([DataTime], [Symbol], [BaseExchange], [TargetExchange])
    );
    CREATE INDEX [IX_StrongBuySignals_DetectedAt] ON [dbo].[StrongBuySignals] ([DetectedAt] DESC);
END
GO

PRINT 'StrongBuySignals is ready.';
GO
