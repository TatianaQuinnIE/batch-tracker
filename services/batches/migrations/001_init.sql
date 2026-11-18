-- Batches schema, ported from the Assignment 1 SQLite table.
-- SQLite -> SQL Server: INTEGER PRIMARY KEY AUTOINCREMENT -> INT IDENTITY,
-- TEXT -> NVARCHAR with a length, ISO date text -> DATE.
CREATE TABLE dbo.batches (
    id INT IDENTITY(1, 1) NOT NULL CONSTRAINT pk_batches PRIMARY KEY,
    batch_code NVARCHAR(40) NOT NULL CONSTRAINT uq_batches_batch_code UNIQUE,
    product NVARCHAR(120) NOT NULL,
    produced_on DATE NOT NULL,
    expires_on DATE NOT NULL,
    quantity INT NOT NULL CONSTRAINT ck_batches_quantity CHECK (quantity >= 0),
    CONSTRAINT ck_batches_dates CHECK (expires_on > produced_on)
);

-- One row that GET /health updates, to prove the service can write to its database.
CREATE TABLE dbo.health_check (
    id INT NOT NULL CONSTRAINT pk_health_check PRIMARY KEY,
    checked_at DATETIME2 NOT NULL
);

INSERT INTO dbo.health_check (id, checked_at) VALUES (1, SYSUTCDATETIME());
