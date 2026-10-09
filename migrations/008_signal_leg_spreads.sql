-- ==================================================================
-- 強力買紀錄加上兩邊各自的買賣價差（偵測當下即時訂單簿）
--   SpotSpreadPct     = (現貨 Ask − 現貨 Bid) / 現貨 Bid × 100   （買入端交易所）
--   ContractSpreadPct = (合約 Ask − 合約 Bid) / 合約 Bid × 100   （放空端交易所）
-- 任一邊價差過大（洗盤 / 套利陷阱）開倉那一刻就注定虧在價差上，不開倉
-- 可重複執行
-- ==================================================================

USE [Crypto];
GO

IF COL_LENGTH('dbo.StrongBuySignals', 'SpotSpreadPct') IS NULL
    ALTER TABLE [dbo].[StrongBuySignals] ADD [SpotSpreadPct] DECIMAL(18, 6) NULL;
GO
IF COL_LENGTH('dbo.StrongBuySignals', 'ContractSpreadPct') IS NULL
    ALTER TABLE [dbo].[StrongBuySignals] ADD [ContractSpreadPct] DECIMAL(18, 6) NULL;
GO

PRINT 'StrongBuySignals leg spread columns are ready.';
GO
