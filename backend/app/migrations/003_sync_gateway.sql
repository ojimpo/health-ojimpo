-- Phase 3: Activate sync-gateway sources (Filmarks, 読書メーター)
UPDATE source_settings SET status = 'active', phase = 'phase3' WHERE id IN ('filmarks', 'bookmeter');
