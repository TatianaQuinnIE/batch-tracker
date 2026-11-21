-- A batch can be recalled: pulled from sale on a date, for a reason, without deleting
-- it (its feedback still points at its code). Applied to a table that already holds
-- data, so both columns are NULL-able: every existing row stays as it was and reads
-- as "not recalled", and nothing has to be backfilled.
--
-- Expand only (ADR-10): no column is renamed or dropped, so the previous revision,
-- which names its columns explicitly, keeps working while this one rolls out and
-- after a rollback of the code.
ALTER TABLE dbo.batches ADD
    recalled_on DATE NULL,
    recall_reason NVARCHAR(200) NULL;
GO
-- In a separate batch because it names the columns added above. It is checked
-- against the existing rows too, which pass because both columns are NULL there.
ALTER TABLE dbo.batches ADD CONSTRAINT ck_batches_recall CHECK (
    (recalled_on IS NULL AND recall_reason IS NULL)
    OR (recalled_on IS NOT NULL AND recall_reason IS NOT NULL)
);
