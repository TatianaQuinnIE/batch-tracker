-- Local development only: run by the one-off db-init service in docker-compose.yml.
-- Creates one database per service and one login per service that can only use
-- its own database. Idempotent: running it again changes nothing except resetting
-- the passwords to the values passed in.
--
-- $(BATCHES_DB_PASSWORD) and $(FEEDBACK_DB_PASSWORD) are sqlcmd variables, read
-- from environment variables of the same name, so no password is written here.
-- On Azure the same logins are created once by hand (README, "Initial Azure setup").

IF DB_ID(N'batches') IS NULL CREATE DATABASE batches;
IF DB_ID(N'feedback') IS NULL CREATE DATABASE feedback;
GO

IF SUSER_ID(N'batches_app') IS NULL
    CREATE LOGIN batches_app WITH PASSWORD = N'$(BATCHES_DB_PASSWORD)', CHECK_POLICY = ON;
ELSE
    ALTER LOGIN batches_app WITH PASSWORD = N'$(BATCHES_DB_PASSWORD)';

IF SUSER_ID(N'feedback_app') IS NULL
    CREATE LOGIN feedback_app WITH PASSWORD = N'$(FEEDBACK_DB_PASSWORD)', CHECK_POLICY = ON;
ELSE
    ALTER LOGIN feedback_app WITH PASSWORD = N'$(FEEDBACK_DB_PASSWORD)';
GO

-- Each login becomes a user only in its own database. It gets DDL rights (to run
-- its migrations) and read/write on data, but not db_owner, and no user at all in
-- the other service's database, so it cannot even open it.
USE batches;
IF USER_ID(N'batches_app') IS NULL CREATE USER batches_app FOR LOGIN batches_app;
ALTER ROLE db_ddladmin ADD MEMBER batches_app;
ALTER ROLE db_datareader ADD MEMBER batches_app;
ALTER ROLE db_datawriter ADD MEMBER batches_app;
GO

USE feedback;
IF USER_ID(N'feedback_app') IS NULL CREATE USER feedback_app FOR LOGIN feedback_app;
ALTER ROLE db_ddladmin ADD MEMBER feedback_app;
ALTER ROLE db_datareader ADD MEMBER feedback_app;
ALTER ROLE db_datawriter ADD MEMBER feedback_app;
GO

PRINT 'db/init.sql done: databases batches and feedback, logins batches_app and feedback_app';
