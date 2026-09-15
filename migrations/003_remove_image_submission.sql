ALTER TABLE reports
    DROP COLUMN IF EXISTS has_image,
    DROP COLUMN IF EXISTS image_data;
