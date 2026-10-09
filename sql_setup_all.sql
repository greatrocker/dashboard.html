-- ==================================================================
-- 多交易所市場監控系統 - 一次性建置腳本
-- 用途：在 SQL Server Management Studio (或 sqlcmd) 對現有 MSSQL 執行
-- 會建立 Crypto 資料庫（若不存在）、5 個交易所的 Table 與對應 Stored Procedure
-- 交易所：Bybit / Binance / OKX / MEXC / Gate.io
-- ==================================================================

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = N'Crypto')
BEGIN
    CREATE DATABASE [Crypto];
END
GO

USE [Crypto];
GO

-- ==================================================================
-- 通用схема（Bybit / Binance / OKX / MEXC 共用同一組欄位命名）
-- ==================================================================

-- ---------- Bybit ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Bybit]') AND type = N'U')
BEGIN
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
END
GO

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
GO

-- ---------- Binance ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Binance]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[Binance] (
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

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_binance]
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

        MERGE INTO dbo.Binance AS md
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
        RAISERROR('Error in merge_market_data_binance: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- OKX ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[OKX]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[OKX] (
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

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_okx]
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

        MERGE INTO dbo.OKX AS md
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
        RAISERROR('Error in merge_market_data_okx: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- MEXC ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[MEXC]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[MEXC] (
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

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_mexc]
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

        MERGE INTO dbo.MEXC AS md
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
        RAISERROR('Error in merge_market_data_mexc: %s', 16, 1, @ErrMsg);
    END CATCH
END;
GO

-- ---------- Gate.io（欄位命名與其他交易所不同，沿用專案內 sql_gate_setup.sql 的定義） ----------
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Gate]') AND type = N'U')
BEGIN
    CREATE TABLE [dbo].[Gate] (
        [Time]              DATETIME        NOT NULL,
        [Symbol]            NVARCHAR(20)    NOT NULL,
        [GateSpot_bids]     DECIMAL(20, 8)  NULL,
        [GateSpot_asks]     DECIMAL(20, 8)  NULL,
        [GateContract_bids] DECIMAL(20, 8)  NULL,
        [GateContract_asks] DECIMAL(20, 8)  NULL,
        [Open_position_Gap]     DECIMAL(20, 8)  NULL,
        [Close_position_Gap]    DECIMAL(20, 8)  NULL,
        [Open_position_Gap2nd]  DECIMAL(20, 8)  NULL,
        [Close_position_Gap2nd] DECIMAL(20, 8)  NULL,
        CONSTRAINT [PK_Gate] PRIMARY KEY CLUSTERED ([Time] ASC, [Symbol] ASC)
    );
END
GO

CREATE OR ALTER PROCEDURE [dbo].[merge_market_data_gate]
    @Time              DATETIME,
    @Symbol            NVARCHAR(20),
    @GateSpot_bids     DECIMAL(20, 8),
    @GateSpot_asks     DECIMAL(20, 8),
    @GateContract_bids DECIMAL(20, 8),
    @GateContract_asks DECIMAL(20, 8)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @OpenGap    DECIMAL(20, 8) = NULL;
    DECLARE @CloseGap   DECIMAL(20, 8) = NULL;
    DECLARE @OpenGap2   DECIMAL(20, 8) = NULL;
    DECLARE @CloseGap2  DECIMAL(20, 8) = NULL;

    IF @GateContract_bids IS NOT NULL AND @GateSpot_asks IS NOT NULL AND @GateSpot_asks <> 0
        SET @OpenGap = (@GateContract_bids - @GateSpot_asks) / @GateSpot_asks * 100;

    IF @GateSpot_bids IS NOT NULL AND @GateContract_asks IS NOT NULL AND @GateContract_asks <> 0
        SET @CloseGap = (@GateSpot_bids - @GateContract_asks) / @GateContract_asks * 100;

    IF @GateSpot_asks IS NOT NULL AND @GateContract_bids IS NOT NULL AND @GateContract_bids <> 0
        SET @OpenGap2 = (@GateSpot_asks - @GateContract_bids) / @GateContract_bids * 100;

    IF @GateContract_asks IS NOT NULL AND @GateSpot_bids IS NOT NULL AND @GateSpot_bids <> 0
        SET @CloseGap2 = (@GateContract_asks - @GateSpot_bids) / @GateSpot_bids * 100;

    MERGE [dbo].[Gate] AS target
    USING (SELECT @Time AS [Time], @Symbol AS [Symbol]) AS source
    ON target.[Time] = source.[Time] AND target.[Symbol] = source.[Symbol]
    WHEN MATCHED THEN
        UPDATE SET
            [GateSpot_bids]         = @GateSpot_bids,
            [GateSpot_asks]         = @GateSpot_asks,
            [GateContract_bids]     = @GateContract_bids,
            [GateContract_asks]     = @GateContract_asks,
            [Open_position_Gap]     = @OpenGap,
            [Close_position_Gap]    = @CloseGap,
            [Open_position_Gap2nd]  = @OpenGap2,
            [Close_position_Gap2nd] = @CloseGap2
    WHEN NOT MATCHED THEN
        INSERT ([Time], [Symbol], [GateSpot_bids], [GateSpot_asks],
                [GateContract_bids], [GateContract_asks],
                [Open_position_Gap], [Close_position_Gap],
                [Open_position_Gap2nd], [Close_position_Gap2nd])
        VALUES (@Time, @Symbol, @GateSpot_bids, @GateSpot_asks,
                @GateContract_bids, @GateContract_asks,
                @OpenGap, @CloseGap, @OpenGap2, @CloseGap2);
END;
GO

PRINT 'All exchange tables and stored procedures are ready.';
GO
