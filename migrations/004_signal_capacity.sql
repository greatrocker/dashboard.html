-- ==================================================================
-- 強力買紀錄加上「可套利金額」：偵測當下查兩邊即時訂單簿，
-- 在 Open Gap 仍 > MIN_OPEN_GAP 的前提下可成交的金額（USDT）與幣量
-- 可重複執行
-- ==================================================================

USE [Crypto];
GO

IF COL_LENGTH('dbo.StrongBuySignals', 'CapacityUsd') IS NULL
    ALTER TABLE [dbo].[StrongBuySignals] ADD [CapacityUsd] DECIMAL(18, 2) NULL;
GO
IF COL_LENGTH('dbo.StrongBuySignals', 'CapacityQty') IS NULL
    ALTER TABLE [dbo].[StrongBuySignals] ADD [CapacityQty] DECIMAL(28, 10) NULL;
GO

PRINT 'StrongBuySignals capacity columns are ready.';
GO
