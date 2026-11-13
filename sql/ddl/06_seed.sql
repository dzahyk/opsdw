-- Static reference data (synthetic business rules, real city geography).
INSERT INTO core.dim_city (city_key, city_code, city_name, province, island) VALUES
    (-1, 'UNK', 'Unknown', 'Unknown', 'Unknown'),
    (1, 'JKT', 'Jakarta',    'DKI Jakarta',     'Java'),
    (2, 'BDG', 'Bandung',    'Jawa Barat',      'Java'),
    (3, 'SBY', 'Surabaya',   'Jawa Timur',      'Java'),
    (4, 'SMG', 'Semarang',   'Jawa Tengah',     'Java'),
    (5, 'YOG', 'Yogyakarta', 'DI Yogyakarta',   'Java'),
    (6, 'MDN', 'Medan',      'Sumatera Utara',  'Sumatra')
ON CONFLICT (city_key) DO NOTHING;

INSERT INTO core.ref_commission_tier VALUES
    ('bronze', 0.2000), ('silver', 0.1700), ('gold', 0.1500)
ON CONFLICT DO NOTHING;

INSERT INTO core.dim_date
SELECT to_char(d, 'YYYYMMDD')::int, d, extract(year FROM d), extract(quarter FROM d), extract(month FROM d),
       date_trunc('month', d)::date, to_char(d, 'YYYY-MM'), extract(week FROM d), extract(isodow FROM d),
       to_char(d, 'FMDay'), extract(isodow FROM d) IN (6, 7)
FROM generate_series(date '2023-01-01', date '2026-12-31', interval '1 day') AS g(d)
ON CONFLICT DO NOTHING;

-- Unknown members (key -1) so facts never drop rows when a dimension record is late.
INSERT INTO core.dim_customer (customer_key, customer_id, is_inferred) VALUES (-1, '__unknown__', true) ON CONFLICT DO NOTHING;
INSERT INTO core.dim_courier (courier_key, courier_id) VALUES (-1, '__unassigned__') ON CONFLICT DO NOTHING;
INSERT INTO core.dim_merchant (merchant_key, merchant_id, version_no, valid_from, valid_to, is_current)
VALUES (-1, '__unknown__', 1, '-infinity', 'infinity', true) ON CONFLICT DO NOTHING;
