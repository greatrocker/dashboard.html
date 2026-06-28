-- Gate.io 建表與 Stored Procedure
-- 在 SQL Server Management Studio 執行此腳本 (資料庫: Crypto)

USE [Crypto];
GO

-- 建立 Gate 資料表
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
    PRINT 'Table [Gate] created.';
END
ELSE
    PRINT 'Table [Gate] already exists.';
GO

-- 建立 Stored Procedure
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

    -- Open Gap:  (Contract_bid - Spot_ask) / Spot_ask * 100
    IF @GateContract_bids IS NOT NULL AND @GateSpot_asks IS NOT NULL AND @GateSpot_asks <> 0
        SET @OpenGap = (@GateContract_bids - @GateSpot_asks) / @GateSpot_asks * 100;

    -- Close Gap: (Spot_bid - Contract_ask) / Contract_ask * 100
    IF @GateSpot_bids IS NOT NULL AND @GateContract_asks IS NOT NULL AND @GateContract_asks <> 0
        SET @CloseGap = (@GateSpot_bids - @GateContract_asks) / @GateContract_asks * 100;

    -- Open Gap 2nd:  (Spot_ask - Contract_bid) / Contract_bid * 100
    IF @GateSpot_asks IS NOT NULL AND @GateContract_bids IS NOT NULL AND @GateContract_bids <> 0
        SET @OpenGap2 = (@GateSpot_asks - @GateContract_bids) / @GateContract_bids * 100;

    -- Close Gap 2nd: (Contract_ask - Spot_bid) / Spot_bid * 100
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

PRINT 'Gate.io setup complete.';
