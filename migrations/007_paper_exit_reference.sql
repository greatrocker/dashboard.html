-- ==================================================================
-- 模擬交易：記錄「平倉決策當下」的參考報價，用來計算平倉執行滑價
--   ExitRefSpotBid / ExitRefContractAsk：觸發平倉條件那一刻的現貨 Bid、合約 Ask（最新行情）
--   ExitDecidedAt                     ：觸發平倉條件的行情時間
-- 平倉成交價（ExitSpotPrice / ExitContractPrice）是之後查即時訂單簿逐檔成交的結果
-- 可重複執行
-- ==================================================================

USE [Crypto];
GO

IF COL_LENGTH('dbo.PaperTrades', 'ExitRefSpotBid') IS NULL
    ALTER TABLE [dbo].[PaperTrades] ADD [ExitRefSpotBid] DECIMAL(28, 10) NULL;
GO
IF COL_LENGTH('dbo.PaperTrades', 'ExitRefContractAsk') IS NULL
    ALTER TABLE [dbo].[PaperTrades] ADD [ExitRefContractAsk] DECIMAL(28, 10) NULL;
GO
IF COL_LENGTH('dbo.PaperTrades', 'ExitDecidedAt') IS NULL
    ALTER TABLE [dbo].[PaperTrades] ADD [ExitDecidedAt] DATETIME NULL;
GO

PRINT 'PaperTrades exit reference columns are ready.';
GO
