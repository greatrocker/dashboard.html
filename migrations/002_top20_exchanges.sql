-- ==================================================================
-- 前 20 大交易所擴充：新增 15 家交易所的 Table 與 Stored Procedure
-- 結構與 README 的 Bybit 範本完全相同（由 sql_setup_all.sql 的 Bybit 區段產生）
-- 可重複執行（IF NOT EXISTS / CREATE OR ALTER）
-- ==================================================================

USE [Crypto];
GO

-- ---------- Bitget ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Bitget]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[Bitget] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_bitget]
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

        MERGE INTO dbo.Bitget AS md
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
        RAISERROR('Error in merge_market_data_bitget: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- KuCoin ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[KuCoin]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[KuCoin] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_kucoin]
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

        MERGE INTO dbo.KuCoin AS md
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
        RAISERROR('Error in merge_market_data_kucoin: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- HTX ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[HTX]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[HTX] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_htx]
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

        MERGE INTO dbo.HTX AS md
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
        RAISERROR('Error in merge_market_data_htx: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- BingX ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[BingX]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[BingX] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_bingx]
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

        MERGE INTO dbo.BingX AS md
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
        RAISERROR('Error in merge_market_data_bingx: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- CryptoCom ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[CryptoCom]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[CryptoCom] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_cryptocom]
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

        MERGE INTO dbo.CryptoCom AS md
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
        RAISERROR('Error in merge_market_data_cryptocom: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- Kraken ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Kraken]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[Kraken] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_kraken]
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

        MERGE INTO dbo.Kraken AS md
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
        RAISERROR('Error in merge_market_data_kraken: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- Coinbase ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Coinbase]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[Coinbase] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_coinbase]
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

        MERGE INTO dbo.Coinbase AS md
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
        RAISERROR('Error in merge_market_data_coinbase: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- Bitfinex ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Bitfinex]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[Bitfinex] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_bitfinex]
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

        MERGE INTO dbo.Bitfinex AS md
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
        RAISERROR('Error in merge_market_data_bitfinex: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- WhiteBIT ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[WhiteBIT]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[WhiteBIT] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_whitebit]
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

        MERGE INTO dbo.WhiteBIT AS md
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
        RAISERROR('Error in merge_market_data_whitebit: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- XT ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[XT]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[XT] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_xt]
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

        MERGE INTO dbo.XT AS md
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
        RAISERROR('Error in merge_market_data_xt: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- Phemex ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Phemex]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[Phemex] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_phemex]
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

        MERGE INTO dbo.Phemex AS md
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
        RAISERROR('Error in merge_market_data_phemex: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- Poloniex ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Poloniex]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[Poloniex] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_poloniex]
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

        MERGE INTO dbo.Poloniex AS md
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
        RAISERROR('Error in merge_market_data_poloniex: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- Deepcoin ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Deepcoin]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[Deepcoin] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_deepcoin]
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

        MERGE INTO dbo.Deepcoin AS md
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
        RAISERROR('Error in merge_market_data_deepcoin: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- Toobit ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Toobit]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[Toobit] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_toobit]
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

        MERGE INTO dbo.Toobit AS md
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
        RAISERROR('Error in merge_market_data_toobit: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- Pionex ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Pionex]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[Pionex] (
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
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_pionex]
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

        MERGE INTO dbo.Pionex AS md
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
        RAISERROR('Error in merge_market_data_pionex: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

PRINT 'Top-20 exchange tables and stored procedures are ready.';
GO
