-- Preserve historical evidence and runs while retiring unfinished visual readings.
UPDATE runs SET state='interrupted', finished_at=now(), error_code='stage_retired'
WHERE state='running' AND job_id IN (SELECT id FROM jobs WHERE stage='lights');

UPDATE jobs SET state='failed', lease_token=NULL, lease_until=NULL, updated_at=now()
WHERE stage='lights' AND state IN ('pending','running');
