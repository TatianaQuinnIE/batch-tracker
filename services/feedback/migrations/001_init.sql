-- Feedback schema, ported from the Assignment 1 SQLite table.
-- batch_code is plain text with no foreign key: the batches table lives in the
-- batches service's own database (ADR-3, ADR-6).
CREATE TABLE dbo.feedback (
    id INT IDENTITY(1, 1) NOT NULL CONSTRAINT pk_feedback PRIMARY KEY,
    batch_code NVARCHAR(40) NOT NULL,
    rating INT NOT NULL CONSTRAINT ck_feedback_rating CHECK (rating BETWEEN 1 AND 5),
    had_reaction BIT NOT NULL,
    comment NVARCHAR(1000) NOT NULL CONSTRAINT df_feedback_comment DEFAULT N'',
    submitted_on DATE NOT NULL
);

CREATE INDEX ix_feedback_batch_code ON dbo.feedback (batch_code);

-- One row that GET /health updates, to prove the service can write to its database.
CREATE TABLE dbo.health_check (
    id INT NOT NULL CONSTRAINT pk_health_check PRIMARY KEY,
    checked_at DATETIME2 NOT NULL
);

INSERT INTO dbo.health_check (id, checked_at) VALUES (1, SYSUTCDATETIME());
