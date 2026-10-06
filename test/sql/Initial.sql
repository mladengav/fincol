IF OBJECT_ID(N'[__EFMigrationsHistory]') IS NULL
BEGIN
    CREATE TABLE [__EFMigrationsHistory] (
        [MigrationId] nvarchar(150) NOT NULL,
        [ProductVersion] nvarchar(32) NOT NULL,
        CONSTRAINT [PK___EFMigrationsHistory] PRIMARY KEY ([MigrationId])
    );
END;
GO

BEGIN TRANSACTION;
IF SCHEMA_ID(N'stocko') IS NULL EXEC(N'CREATE SCHEMA [stocko];');

CREATE TABLE [stocko].[TickerSnapshots] (
    [SnapshotDate] date NOT NULL,
    [Symbol] nvarchar(10) NOT NULL,
    [SectorKey] nvarchar(255) NOT NULL,
    [IndustryKey] nvarchar(255) NOT NULL,
    [Industry] nvarchar(255) NOT NULL,
    [Sector] nvarchar(255) NOT NULL,
    [ExDividendDate] date NULL,
    [LastDividendDate] date NOT NULL,
    [LongName] nvarchar(255) NOT NULL,
    [RegularMarketPrice] decimal(19,4) NOT NULL,
    [RegularMarketTime] bigint NOT NULL,
    [DividendRate] decimal(19,4) NOT NULL,
    [DividendYield] float NOT NULL,
    [MarketCap] bigint NOT NULL,
    [PayoutRatio] float NOT NULL,
    [HeldPercentInsiders] float NOT NULL,
    [HeldPercentInstitutions] float NOT NULL,
    [QuoteType] nvarchar(255) NOT NULL,
    [TypeDisp] nvarchar(255) NOT NULL,
    [LastDividendDecrease] date NOT NULL,
    [YearsSinceDividendDecrease] int NOT NULL,
    [YearsConsecutiveDividendIncrease] int NOT NULL,
    [TtmDivs] decimal(19,4) NOT NULL,
    CONSTRAINT [PK_TickerSnapshots] PRIMARY KEY ([Symbol], [SnapshotDate])
);

INSERT INTO [__EFMigrationsHistory] ([MigrationId], [ProductVersion])
VALUES (N'20261002162314_Initial', N'10.0.12');

COMMIT;
GO

