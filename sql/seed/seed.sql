-- Idempotent reference data applied on every API boot (ON CONFLICT DO NOTHING).
-- Copy comes from the KaaamNow Figma file; marketplace values are OWNER DECISIONS.

-- Figma SH · Language
INSERT INTO languages (code, english_name, native_name, sort_order) VALUES
    ('en', 'English',   'English',   1),
    ('hi', 'Hindi',     'हिन्दी',      2),
    ('ta', 'Tamil',     'தமிழ்',      3),
    ('te', 'Telugu',    'తెలుగు',     4),
    ('kn', 'Kannada',   'ಕನ್ನಡ',      5),
    ('ml', 'Malayalam', 'മലയാളം',    6),
    ('mr', 'Marathi',   'मराठी',      7),
    ('bn', 'Bengali',   'বাংলা',      8),
    ('gu', 'Gujarati',  'ગુજરાતી',    9),
    ('pa', 'Punjabi',   'ਪੰਜਾਬੀ',     10),
    ('or', 'Odia',      'ଓଡ଼ିଆ',      11),
    ('ur', 'Urdu',      'اردو',      12)
ON CONFLICT (code) DO NOTHING;

-- Figma "Work type" / "Business type" chips, plus unorganised-sector daily work.
INSERT INTO work_categories (slug, name, icon, sort_order) VALUES
    ('hospitality',      'Hospitality',              'coffee',        1),
    ('retail',           'Retail',                   'shopping-bag',  2),
    ('events',           'Events',                   'calendar',      3),
    ('delivery',         'Delivery',                 'truck',         4),
    ('house-help',       'House Help / Maid',        'home',          5),
    ('cooking',          'Cook',                     'chef-hat',      6),
    ('cleaning',         'Cleaning',                 'sparkles',      7),
    ('babysitting',      'Babysitting / Nanny',      'baby',          8),
    ('elder-care',       'Elder Care',               'heart-handshake', 9),
    ('driver',           'Driver',                   'car',           10),
    ('security',         'Security Guard',           'shield',        11),
    ('construction',     'Construction Labour',      'hard-hat',      12),
    ('loading',          'Loading / Unloading',      'package',       13),
    ('warehouse',        'Warehouse Helper',         'warehouse',     14),
    ('gardening',        'Gardening',                'leaf',          15),
    ('painting',         'Painter',                  'paintbrush',    16),
    ('plumbing',         'Plumber',                  'wrench',        17),
    ('electrician',      'Electrician',              'zap',           18),
    ('carpentry',        'Carpenter',                'hammer',        19),
    ('tailoring',        'Tailoring',                'scissors',      20),
    ('laundry',          'Laundry / Ironing',        'shirt',         21),
    ('kitchen-helper',   'Kitchen Helper',           'utensils',      22),
    ('waiter',           'Waiter / Server',          'concierge-bell', 23),
    ('shop-helper',      'Shop Helper',              'store',         24),
    ('office-boy',       'Office Assistant / Peon',  'briefcase',     25),
    ('car-wash',         'Car Wash',                 'droplets',      26),
    ('pet-care',         'Pet Care',                 'paw-print',     27),
    ('cook',             'Cook (Hotel / Restaurant)', 'chef-hat',     28),
    ('hotel-staff',      'Hotel Staff',              'bed',           29),
    ('ac-technician',           'AC Technician / Repair',          'air-vent',        30),
    ('appliance-repair',        'Appliance Repair Technician',     'plug',            31),
    ('ro-technician',           'RO / Water Purifier Technician',  'droplet',         32),
    ('pest-control',            'Pest Control Worker',             'bug',             33),
    ('deep-cleaning',           'Deep Cleaning',                   'spray-can',       34),
    ('chef',                    'Chef / Head Cook',                'chef-hat',        35),
    ('dishwasher',              'Dishwasher / Kitchen Steward',    'utensils-crossed', 36),
    ('catering-staff',          'Catering Staff',                  'utensils',        37),
    ('barista',                 'Barista',                         'coffee',          38),
    ('cashier',                 'Cashier / Billing Staff',         'receipt',         39),
    ('sales-executive',         'Sales Executive',                 'trending-up',     40),
    ('storekeeper',             'Storekeeper',                     'boxes',           41),
    ('inventory-assistant',     'Inventory Assistant',             'clipboard-list',  42),
    ('receptionist',            'Receptionist / Front Desk',       'bell',            43),
    ('data-entry',              'Data Entry Operator',             'keyboard',        44),
    ('computer-operator',       'Computer Operator',               'monitor',         45),
    ('customer-support',        'Customer Support Executive',      'headphones',      46),
    ('bike-delivery',           'Bike Delivery Partner',           'bike',            47),
    ('courier',                 'Courier / Parcel Delivery',       'package',         48),
    ('picker-packer',           'Picker / Packer',                 'package-check',   49),
    ('forklift-operator',       'Forklift Operator',               'forklift',        50),
    ('factory-helper',          'Factory Helper',                  'factory',         51),
    ('machine-operator',        'Machine Operator',                'cog',             52),
    ('production-line',         'Production Line Worker',          'settings',        53),
    ('packaging',               'Packaging Worker',                'package-open',    54),
    ('quality-checker',         'Quality Checker',                 'badge-check',     55),
    ('mason',                   'Mason / Raj Mistri',              'brick-wall',      56),
    ('tile-fitter',             'Tile / Marble Fitter',            'grid-3x3',        57),
    ('welder',                  'Welder',                          'flame',           58),
    ('fabricator',              'Fabricator',                      'wrench',          59),
    ('false-ceiling',           'False Ceiling Worker',            'layers',          60),
    ('glass-fitter',            'Glass / Aluminium Fitter',        'square',          61),
    ('construction-supervisor', 'Construction Supervisor',         'hard-hat',        62),
    ('event-setup',             'Event Setup Crew',                'tent',            63),
    ('sound-light',             'Sound / Light Technician',        'speaker',         64),
    ('photographer',            'Photographer / Videographer',     'camera',          65),
    ('housekeeping',            'Housekeeping Staff',              'bed-double',      66),
    ('facility-maintenance',    'Facility Maintenance Technician', 'hammer',          67),
    ('beautician',              'Beautician / Salon Staff',        'sparkle',         68),
    ('barber',                  'Hairdresser / Barber',            'scissors',        69),
    ('makeup-artist',           'Makeup Artist',                   'brush',           70),
    ('mobile-repair',           'Mobile Repair Technician',        'smartphone',      71),
    ('it-technician',           'Computer / IT Technician',        'laptop',          72),
    ('tutor',                   'Tutor / Home Tutor',              'book-open',       73),
    ('waste-collection',        'Waste Collection Worker',         'trash-2',         74),
    ('other',            'Other',                    'more-horizontal', 99)
ON CONFLICT (slug) DO NOTHING;

-- Business / Work type chips: one list for households and commercial hirers alike.
INSERT INTO business_types (slug, name, icon, sort_order) VALUES
    ('household',             'Household',                         'home',            1),
    ('personal-residence',    'Personal Residence',                'house',           2),
    ('apartment',             'Apartment / Flat',                  'building-2',      3),
    ('independent-house',     'Independent House / Villa',         'house-plus',      4),
    ('rental-property',       'Rental Property',                   'key-round',       5),
    ('residential-society',   'Residential Society',               'building',        6),
    ('office',                'Office',                            'briefcase',       7),
    ('corporate-office',      'Corporate Office',                  'landmark',        8),
    ('hospitality',           'Hospitality',                       'coffee',          9),
    ('retail',                'Retail',                            'shopping-bag',    10),
    ('events',                'Events',                            'calendar',        11),
    ('delivery',              'Delivery',                          'truck',           12),
    ('restaurant',            'Restaurant / Cafe',                 'utensils',        13),
    ('hotel',                 'Hotel / Guest House',               'bed',             14),
    ('catering',              'Catering',                          'chef-hat',        15),
    ('grocery',               'Grocery / Kirana Store',            'shopping-cart',   16),
    ('supermarket',           'Supermarket / Mall',                'store',           17),
    ('warehouse',             'Warehouse / Logistics',             'warehouse',       18),
    ('manufacturing',         'Factory / Manufacturing',           'factory',         19),
    ('construction',          'Construction',                      'hard-hat',        20),
    ('real-estate',           'Real Estate / Property Management', 'building',        21),
    ('healthcare',            'Hospital / Clinic',                 'stethoscope',     22),
    ('education',             'School / Coaching',                 'graduation-cap',  23),
    ('college',               'College / University',              'school',          24),
    ('salon',                 'Salon / Spa',                       'scissors',        25),
    ('gym',                   'Gym / Fitness Center',              'dumbbell',        26),
    ('cleaning',              'Cleaning / Facility Management',    'sparkles',        27),
    ('security',              'Security Services',                 'shield',          28),
    ('automobile',            'Automobile / Garage',               'car',             29),
    ('car-wash',              'Car Wash',                          'droplets',        30),
    ('laundry',               'Laundry / Dry Cleaning',            'shirt',           31),
    ('bakery',                'Bakery / Sweet Shop',               'cake',            32),
    ('pharmacy',              'Pharmacy',                          'pill',            33),
    ('ecommerce',             'E-commerce',                        'package',         34),
    ('agriculture',           'Farm / Agriculture',                'leaf',            35),
    ('wedding',               'Wedding / Banquet Hall',            'party-popper',    36),
    ('travel',                'Travel / Tourism',                  'plane',           37),
    ('call-center',           'Call Center / BPO',                 'headset',         38),
    ('it-software',           'IT / Software Company',             'laptop',          39),
    ('professional-services', 'Professional Services',             'briefcase-business', 40),
    ('ngo',                   'NGO / Non-profit',                  'hand-heart',      41),
    ('small-business',        'Shop / Small Business',             'store',           42),
    ('other',                 'Other',                             'more-horizontal', 99)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO shift_filter_options
    (filter_type, slug, label, min_value, max_value, sort_order)
VALUES
    ('distance', 'within-1-km', 'Within 1 km', NULL, 1, 1),
    ('distance', 'within-3-km', 'Within 3 km', NULL, 3, 2),
    ('distance', 'within-5-km', 'Within 5 km', NULL, 5, 3),
    ('minimum_pay', '130-per-hour', '₹130+ / hr', 130, NULL, 1),
    ('minimum_pay', '150-per-hour', '₹150+ / hr', 150, NULL, 2),
    ('minimum_pay', '175-per-hour', '₹175+ / hr', 175, NULL, 3),
    ('shift_length', 'up-to-4-hours', 'Up to 4 hours', 0, 4, 1),
    ('shift_length', '5-to-6-hours', '5–6 hours', 5, 6, 2),
    ('shift_length', '7-plus-hours', '7+ hours', 7, NULL, 3)
ON CONFLICT (filter_type, slug) DO NOTHING;

-- Bring rows seeded by the earlier list to the new names and order. A row an admin has since
-- renamed or reordered no longer matches its old values and is left alone.
UPDATE business_types bt
SET name = v.new_name, sort_order = v.new_sort, updated_at = now()
FROM (VALUES
    ('hospitality',   'Hospitality',             1,  'Hospitality',                       9),
    ('retail',        'Retail',                  2,  'Retail',                            10),
    ('events',        'Events',                  3,  'Events',                            11),
    ('delivery',      'Delivery',                4,  'Delivery',                          12),
    ('household',     'Household',               5,  'Household',                         1),
    ('office',        'Office',                  6,  'Office',                            7),
    ('restaurant',    'Restaurant / Cafe',       7,  'Restaurant / Cafe',                 13),
    ('hotel',         'Hotel / Guest House',     8,  'Hotel / Guest House',               14),
    ('catering',      'Catering',                9,  'Catering',                          15),
    ('grocery',       'Grocery / Kirana Store',  10, 'Grocery / Kirana Store',            16),
    ('supermarket',   'Supermarket / Mall',      11, 'Supermarket / Mall',                17),
    ('warehouse',     'Warehouse / Logistics',   12, 'Warehouse / Logistics',             18),
    ('manufacturing', 'Factory / Manufacturing', 13, 'Factory / Manufacturing',           19),
    ('construction',  'Construction',            14, 'Construction',                      20),
    ('real-estate',   'Real Estate / Society',   15, 'Real Estate / Property Management', 21),
    ('healthcare',    'Hospital / Clinic',       16, 'Hospital / Clinic',                 22),
    ('education',     'School / Coaching',       17, 'School / Coaching',                 23),
    ('salon',         'Salon / Spa',             18, 'Salon / Spa',                       25),
    ('gym',           'Gym / Fitness',           19, 'Gym / Fitness Center',              26),
    ('cleaning',      'Cleaning / Facility',     20, 'Cleaning / Facility Management',    27),
    ('security',      'Security Services',       21, 'Security Services',                 28),
    ('automobile',    'Automobile / Garage',     22, 'Automobile / Garage',               29),
    ('car-wash',      'Car Wash',                23, 'Car Wash',                          30),
    ('laundry',       'Laundry / Dry Clean',     24, 'Laundry / Dry Cleaning',            31),
    ('bakery',        'Bakery / Sweet Shop',     25, 'Bakery / Sweet Shop',               32),
    ('pharmacy',      'Pharmacy',                26, 'Pharmacy',                          33),
    ('ecommerce',     'E-commerce',              27, 'E-commerce',                        34),
    ('agriculture',   'Farm / Agriculture',      28, 'Farm / Agriculture',                35),
    ('wedding',       'Wedding / Banquet Hall',  29, 'Wedding / Banquet Hall',            36)
) AS v(slug, old_name, old_sort, new_name, new_sort)
WHERE bt.slug = v.slug AND bt.name = v.old_name AND bt.sort_order = v.old_sort;

-- Entities that only carry the legacy work-category get the Business / Work type of the same slug.
UPDATE business_profiles bp
SET business_type_id = bt.id, updated_at = now()
FROM work_categories wc
JOIN business_types bt ON bt.slug = wc.slug
WHERE bp.business_type_id IS NULL AND bp.category_id = wc.id;

-- Profiles that predate multi-select keep their single type as the primary chip.
INSERT INTO business_profile_types (business_profile_id, business_type_id, position)
SELECT bp.id, bp.business_type_id, 0
FROM business_profiles bp
WHERE bp.business_type_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM business_profile_types t WHERE t.business_profile_id = bp.id)
ON CONFLICT DO NOTHING;

-- OWNER DECISION: Figma shows an illustrative 5% fee paid by the business on top of worker pay.
INSERT INTO platform_fee_policies (version, percentage, is_active, notes)
SELECT 1, 5.00, true, 'DEV DEFAULT from Figma copy (5% on top of worker pay). Confirm before launch.'
WHERE NOT EXISTS (SELECT 1 FROM platform_fee_policies);

-- Marketplace rules v1: no platform fee; 4% commission from business + 4% from worker;
-- ~2% gateway charge paid by the business. Applied once; later versions come from admin.
UPDATE platform_fee_policies SET is_active = false
WHERE is_active AND NOT EXISTS (SELECT 1 FROM platform_fee_policies WHERE version = 2);
INSERT INTO platform_fee_policies (version, percentage, worker_percentage, gateway_percentage, is_active, notes)
SELECT 2, 4.00, 4.00, 2.00, true, 'Rules v1: 4% business + 4% worker commission, 2% gateway (business).'
WHERE NOT EXISTS (SELECT 1 FROM platform_fee_policies WHERE version = 2);

-- Live Work pricing v1: 4% platform commission, 2% tax on (base amount + commission), 30%
-- extension surcharge. Applied once; later versions come from admin "Live Work Pricing & Charges".
INSERT INTO live_pricing_settings (
    version, commission_pct, tax_pct, tax_label, tax_base, extension_surcharge_pct, is_active,
    changed_by_label, notes
)
SELECT 1, 4.00, 2.00, 'Tax', 'subtotal', 30.00, true, 'system seed',
       'Live Work defaults: 4% commission, 2% tax on base + commission, 30% extension surcharge.'
WHERE NOT EXISTS (SELECT 1 FROM live_pricing_settings);

-- Cancellation rules v1 (docs/marketplace-rules.md §5, §6). Amounts in paise.
INSERT INTO cancellation_policies (version, is_active, notes)
VALUES (1, true, 'Rules v1')
ON CONFLICT (version) DO NOTHING;
INSERT INTO cancellation_policy_tiers (
    policy_version, party, event, hours_from, hours_to, flat_fee_minor, booking_pct,
    fee_cap_minor, worker_share_pct, strike_weight, business_voucher
) VALUES
    (1, 'worker', 'cancel', 12, NULL, 0, 0, NULL, 0, 0, false),
    (1, 'worker', 'cancel', 6, 12, 4900, 0, NULL, 0, 0, false),
    (1, 'worker', 'cancel', 2, 6, 8900, 0, NULL, 0, 0, false),
    (1, 'worker', 'cancel', 0, 2, 14900, 0, NULL, 0, 0.5, true),
    (1, 'worker', 'no_show', 0, NULL, 0, 50, 39900, 0, 1, true),
    (1, 'worker', 'walk_off', 0, NULL, 0, 50, NULL, 0, 0, true),
    (1, 'business', 'cancel', 12, NULL, 0, 0, NULL, 0, 0, false),
    (1, 'business', 'cancel', 6, 12, 0, 50, NULL, 30, 0, false),
    (1, 'business', 'cancel', 2, 6, 0, 70, NULL, 40, 0, false),
    (1, 'business', 'cancel', 0, 2, 0, 100, NULL, 80, 0, false)
ON CONFLICT (policy_version, party, event, hours_from) DO NOTHING;

-- Terms & Conditions (rules in docs/marketplace-rules.md, effective 2026-10-31).
-- A newer version (later effective_date) published from admin is never overwritten.
INSERT INTO content_pages (slug, audience, title, body_markdown, effective_date) VALUES
    ('terms', 'worker', 'Terms & Conditions',
     E'## 1. What KaaamNow is\nKaaamNow is a connecting platform. It connects people and businesses who need work done ("Business") with Workers. KaaamNow is not the employer, does not supervise the work and does not guarantee it. The agreement for the work is between the Business and the Worker; KaaamNow handles matching, payments, the fee rules below and support.\n\n## 2. Accounts\nYou must give accurate details. Your mobile number is verified by OTP. One account can be both a Business and a Worker; each role has its own profile, wallet view and history. You can never book your own work.\n\n## 3. Scheduled shifts\n- Booking is instant: when you book, your place is confirmed. You can book until 2 hours before the start.\n- You cannot hold overlapping shifts. A banned account cannot book.\n- On arrival, enter the 4-character code from the Business to check in. Your location is used only to show nearby work and verify attendance.\n- You are paid after the shift is approved: your pay minus the 4% platform charge.\n- Overtime is paid at 130% of the hourly rate, only when the Business approves it in the app.\n\n## 4. Live Work\n- Live Work requests are instant: the first Worker to accept is booked.\n- On arrival, enter the arrival code from the Business to start the work.\n- When the work is done, ask the Business for the completion code and enter it to finish. Hourly work is paid for the time you actually worked (up to the booked time plus any extra time you accepted); task work is paid the full task price. You receive the pay minus the 4% platform charge.\n- Extra time is offered by the Business; if you accept, it is paid at 130% of the hourly rate.\n\n## 5. Cancellations\nCancellation fees are taken from your wallet. If the wallet goes negative, the amount is recovered from your next earnings, and you can keep working.\n\nScheduled shifts:\n- More than 12 hours before start: free.\n- 12 to 6 hours before: ₹49.\n- 6 to 2 hours before: ₹89.\n- Less than 2 hours before: ₹149 + ½ strike.\n- No-show (no cancel, no message): 50% of your pay (max ₹399) + 1 strike.\n- If the Business cancels, you get compensation: 30% of your pay (12–6 hours before), 40% (6–2 hours) or 80% (less than 2 hours).\n- If you walk off during a shift, you are paid only for the hours worked, minus 4%, minus a penalty of 50% of the booking amount.\n\nLive Work:\n- You cancel after accepting, before you start: ₹149 + ½ strike.\n- The Business cancels before you enter the arrival code: the booking ends and you are not paid.\n- You force-cancel after starting (no code needed): you are not paid for the job.\n- The Business force-cancels after you started (no code needed): you get 80% of the pay.\n\n## 6. Strikes\n2 strikes within 90 days means fewer shifts are shown to you for 7 days; 3 strikes within 90 days means an account ban (our team can review it).\n\n## 7. Privacy and location\nYour location is shared with the Business only while you are travelling to or working at a booked job. See the Privacy Policy for details.\n\n## 8. Ratings and conduct\nBusinesses and Workers rate each other after the work. Harassment, unsafe workplaces, fake check-ins, no-shows or non-payment can lead to suspension or a ban.\n\n## 9. Emergencies and disputes\nEvery booking has an Emergency / Contact support button. Disputes go to support; our team can review and waive or change any fee, strike or voucher for a booking, with a logged reason.\n\n## 10. Changes to these terms\nWhen these terms change, you must accept the new version before your next booking. All amounts and percentages above are the current defaults; the exact amount is always shown in the app before you confirm.\n\n## 11. Contact us\nQuestions about these terms? Write to sumit.pandey@kaaamnow.in or sahil.shrivastava@kaaamnow.in.',
     DATE '2026-10-31'),
    ('terms', 'business', 'Terms & Conditions',
     E'## 1. What KaaamNow is\nKaaamNow is a connecting platform. It connects people and businesses who need work done ("Business") with Workers. KaaamNow is not the employer, does not supervise the work and does not guarantee it. The agreement for the work is between the Business and the Worker; KaaamNow handles matching, payments, the fee rules below and support.\n\n## 2. Accounts\nYou must give accurate details. Your mobile number is verified by OTP. One account can be both a Business and a Worker; each role has its own profile, wallet view and history. You can never book your own work.\n\n## 3. Scheduled shifts\n- A shift must start at least 24 hours after posting and at most 60 days ahead.\n- You pay the full amount when you post: Worker pay + 4% platform charge + the payment gateway charge (about 2%). The money is held until the shift is approved.\n- Workers book instantly until 2 hours before the start. Seats still empty 2 hours before the start are cancelled with a 100% refund for those seats plus a free platform charge voucher.\n- Share the 4-character code with the Worker on arrival so they can check in.\n- Overtime is charged at 130% of the hourly rate, only when you approve it in the app.\n\n## 4. Live Work\n- You pay first: Worker pay + 4% platform charge + 2% tax on (pay + platform charge). Live Work has no payment gateway charge. Nearby Workers get the request and the first to accept is booked.\n- Give the Worker the arrival code when they arrive; the work then starts.\n- When the work is done, give the Worker the completion code. Hourly work is billed only for the time actually worked (up to the booked time plus any paid extra time); the rest of your payment is refunded. Task work is billed at the full task price.\n- Extra time is requested by you, accepted by the Worker and charged at 130% of the hourly rate.\n- If no Worker is found in time, you get a full refund.\n\n## 5. Cancellations\nOn cancellation, the payment gateway charge is non-refundable; the platform charge is refunded together with the refundable part of the pay.\n\nScheduled shifts (percent of the Worker pay; part of it goes to the Worker):\n- No Worker booked yet: free.\n- More than 12 hours before start: free.\n- 12 to 6 hours before: 50% (30% goes to the Worker).\n- 6 to 2 hours before: 70% (40% goes to the Worker).\n- Less than 2 hours before: 100% (80% goes to the Worker).\n- If you stop the work or deny work without reason: you pay 100%; the Worker gets 80%.\n- If a Worker cancels less than 2 hours before, doesn''t show up or walks off, you get a refund and a free platform charge voucher.\n\nLive Work:\n- Before the Worker enters the arrival code (even after they accepted): free, full refund.\n- The Worker cancels before starting: no charge; we look for another Worker.\n- You force-cancel after the Worker started (no code needed): you pay 100%. "End work" without the completion code counts as a force cancel.\n- The Worker force-cancels after starting (no code needed): you are not charged — full refund — and your next Live booking has no platform charge.\n\n## 6. Free platform charge voucher\nThe voucher waives the platform charge and the payment gateway charge on your next booking. It is valid for 60 days, cannot be transferred and is not cash.\n\n## 7. Privacy and location\nA booked Worker''s location is shared with you only while they are travelling to or working at your job. See the Privacy Policy for details.\n\n## 8. Ratings and conduct\nBusinesses and Workers rate each other after the work. Harassment, unsafe workplaces, fake check-ins, no-shows or non-payment can lead to suspension or a ban.\n\n## 9. Emergencies and disputes\nEvery booking has an Emergency / Contact support button. Disputes go to support; our team can review and waive or change any fee, strike or voucher for a booking, with a logged reason.\n\n## 10. Changes to these terms\nWhen these terms change, you must accept the new version before your next booking. All amounts and percentages above are the current defaults; the exact amount is always shown in the app before you confirm.\n\n## 11. Contact us\nQuestions about these terms? Write to sumit.pandey@kaaamnow.in or sahil.shrivastava@kaaamnow.in.',
     DATE '2026-10-31')
ON CONFLICT (slug, audience) DO UPDATE SET
    title = EXCLUDED.title,
    body_markdown = EXCLUDED.body_markdown,
    effective_date = EXCLUDED.effective_date,
    updated_at = now()
WHERE content_pages.effective_date < EXCLUDED.effective_date;

-- FAQ & Help
INSERT INTO faq_entries (audience, question, answer, sort_order) VALUES
    ('worker', 'How do I get paid?',
     'After you check out, the business confirms the shift and your earnings are sent to your UPI or bank account within 24 hours.', 1),
    ('worker', 'How do I cancel a shift?',
     'Open My shifts, choose the shift and tap Cancel. Cancelling less than 12 hours before the start may affect your rating.', 2),
    ('worker', 'How does check-in work?',
     'When you are near the workplace, open the shift and enter the workplace code from your shift lead. Your location is used only to verify attendance.', 3),
    ('worker', 'What if the business doesn’t show up?',
     'Use “I need help checking in” on the shift. Our team will contact the business and keep your earnings safe.', 4),
    ('worker', 'How are ratings calculated?',
     'Your rating is the average of the stars businesses give you after each completed shift.', 5),
    ('business', 'How do I pay for a shift?',
     'After workers check out, review attendance and confirm the final shift cost. Pay with Google Pay, Paytm, UPI QR or card.', 1),
    ('business', 'How do I cancel a shift?',
     'Open Shifts, choose the shift and tap Cancel. Booked workers are notified immediately.', 2),
    ('business', 'How does check-in work?',
     'Each shift has a workplace code. Share it with workers on arrival; they must also be near your workplace to check in.', 3),
    ('business', 'What if a worker doesn’t show up?',
     'After the start time you can mark the worker as a no-show from the roster. You are not charged for no-shows.', 4),
    ('business', 'How are ratings calculated?',
     'Your rating is the average of the stars workers give you after each completed shift.', 5)
ON CONFLICT (audience, question) DO NOTHING;

-- FAQ answers that matched the old rules; only the untouched seed text is replaced.
UPDATE faq_entries SET answer = 'Scheduled shifts: after you check out and the business approves the shift. Live Work: as soon as you finish with the completion code from the business. You receive your pay minus the 4% platform charge, and can withdraw it to your UPI or bank account.', updated_at = now()
WHERE audience = 'worker' AND question = 'How do I get paid?'
  AND answer = 'After you check out, the business confirms the shift and your earnings are sent to your UPI or bank account within 24 hours.';
UPDATE faq_entries SET answer = 'Open the booking and tap Cancel. You see the exact fee before you confirm. Scheduled shifts are free to cancel more than 12 hours before the start; later cancellations cost a fee and, inside 2 hours, a strike. In Live Work, once you have started you can Force cancel without a code, but you are not paid for that job.', updated_at = now()
WHERE audience = 'worker' AND question = 'How do I cancel a shift?'
  AND answer = 'Open My shifts, choose the shift and tap Cancel. Cancelling less than 12 hours before the start may affect your rating.';
UPDATE faq_entries SET answer = 'You pay when you post. Scheduled shifts: Worker pay + 4% platform charge + payment gateway charge, held until the shift is approved. Live Work: Worker pay + 4% platform charge + 2% tax; hourly work is billed only for the time worked and the rest is refunded.', updated_at = now()
WHERE audience = 'business' AND question = 'How do I pay for a shift?'
  AND answer = 'After workers check out, review attendance and confirm the final shift cost. Pay with Google Pay, Paytm, UPI QR or card.';
UPDATE faq_entries SET answer = 'Open the booking and tap Cancel. You see the exact charge and refund before you confirm. In Live Work, once the Worker has started you can Force cancel without a code: you pay the full amount and the Worker gets 80% of the pay.', updated_at = now()
WHERE audience = 'business' AND question = 'How do I cancel a shift?'
  AND answer = 'Open Shifts, choose the shift and tap Cancel. Booked workers are notified immediately.';
UPDATE faq_entries SET answer = 'After the start time you can mark the worker as a no-show from the roster. You get a refund for that Worker and a free platform charge voucher for your next booking.', updated_at = now()
WHERE audience = 'business' AND question = 'What if a worker doesn’t show up?'
  AND answer = 'After the start time you can mark the worker as a no-show from the roster. You are not charged for no-shows.';

UPDATE faq_entries
SET slug = left(trim(BOTH '-' FROM lower(regexp_replace(question, '[^a-zA-Z0-9]+', '-', 'g'))), 64)
WHERE slug IS NULL;
