-- ==================================================================
-- 1) 強力買紀錄加上「獲利空間」(RoundTripPct)：偵測當下即時訂單簿的 Open Gap + Close Gap
--    ≈ −(現貨買賣價差 + 合約買賣價差)，也就是平倉時要付出的價差成本
-- 2) 均值區間改為多種（5 分 ~ 24 小時），同一秒可能有多個區間同時觸發，
--    唯一鍵加入 WindowMinutes
-- 可重複執行
-- ==================================================================

USE [Crypto];
GO

IF COL_LENGTH('dbo.StrongBuySignals', 'RoundTripPct') IS NULL
    ALTER TABLE [dbo].[StrongBuySignals] ADD [RoundTripPct] DECIMAL(18, 6) NULL;
GO

IF EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = 'UQ_StrongBuySignals_Event'
           AND parent_object_id = OBJECT_ID('dbo.StrongBuySignals'))
   AND NOT EXISTS (SELECT 1 FROM sys.index_columns ic
                   JOIN sys.indexes i ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                   JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
                   WHERE i.name = 'UQ_StrongBuySignals_Event' AND c.name = 'WindowMinutes')
BEGIN
    ALTER TABLE [dbo].[StrongBuySignals] DROP CONSTRAINT [UQ_StrongBuySignals_Event];
    ALTER TABLE [dbo].[StrongBuySignals] ADD CONSTRAINT [UQ_StrongBuySignals_Event]
        UNIQUE ([DataTime], [Symbol], [BaseExchange], [TargetExchange], [WindowMinutes]);
END
GO

PRINT 'StrongBuySignals: RoundTripPct + per-window unique key ready.';
GO
