-- Migration 011: Add 'all' to watch_type enum for multi-parameter monitoring.
-- Allows watches that simultaneously monitor wave height, wind, weather,
-- lightning, cyclone alerts, maritime boundaries, and PFZ shifts.
ALTER TYPE watch_type ADD VALUE IF NOT EXISTS 'all';
