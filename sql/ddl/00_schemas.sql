-- Layered warehouse: raw (as landed) -> staging (typed, deduplicated, validated)
-- -> core (conformed star schema) -> mart (additive aggregates) -> bi (semantic views).
CREATE EXTENSION IF NOT EXISTS btree_gist;   -- needed for the SCD2 no-overlap exclusion constraint
CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS bi;
