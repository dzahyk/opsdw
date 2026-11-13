INSERT INTO core.dim_courier (courier_id, city_code, vehicle_type, joined_at, source_updated_at)
SELECT s.courier_id, s.city_code, s.vehicle_type, s.joined_at, s.updated_at
FROM staging.couriers s JOIN chg_couriers c USING (courier_id)
ON CONFLICT (courier_id) DO UPDATE
   SET city_code = EXCLUDED.city_code, vehicle_type = EXCLUDED.vehicle_type, joined_at = EXCLUDED.joined_at,
       source_updated_at = EXCLUDED.source_updated_at;
